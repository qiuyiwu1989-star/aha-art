#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""废图质检:取缩略图算 灰度方差(纯色/空白→低) + 拉普拉斯方差(糊/无内容→低),
低于阈值标 status='reject'(隐藏,可逆)。抓纯白/纯黑/空白页/糊图。
用法: python3 dam_gate.py <lib1,lib2,...> [std_min=8] [lap_min=6] [--limit N]"""
import os, io, json, sys, ssl, socket, urllib.request, urllib.parse
import numpy as np
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED = True
Image.MAX_IMAGE_PIXELS = 60_000_000
import psycopg2
from concurrent.futures import ThreadPoolExecutor

socket.setdefaulttimeout(15)
_SSL = ssl.create_default_context(); _SSL.check_hostname = False; _SSL.verify_mode = ssl.CERT_NONE
IMG_BASE = "https://aha.yishujia.art"; AHA = "aha-1254041526"
args = [x for x in sys.argv[1:] if not x.startswith('--')]
LIBS = args[0].split(',') if args else ['artwork']
STD_MIN = float(args[1]) if len(args) > 1 else 8.0
LAP_MIN = float(args[2]) if len(args) > 2 else 6.0
LIMIT = 0
if '--limit' in sys.argv: LIMIT = int(sys.argv[sys.argv.index('--limit')+1])

d = json.load(open(os.path.expanduser('~/.aha_pg.json')))
cn = psycopg2.connect(host=d['host'], port=d['port'], dbname=d['dbname'], user=d['user'], password=d['password'])
cur = cn.cursor()

def fetch_gray(bucket, ck):
    q = urllib.parse.quote(ck, safe='/')
    base = f"/cimg/{bucket}/{q}" if bucket and bucket != AHA else f"{IMG_BASE}/img/{q}"
    url = (base if base.startswith('http') else "https://dam.alimq.com"+base) + "?imageMogr2/thumbnail/256x"
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":"M"}), timeout=13, context=_SSL).read()
    g = np.asarray(Image.open(io.BytesIO(raw)).convert("L"), dtype=np.float32)
    return g

def metrics(g):
    std = float(g.std())
    lap = 4*g[1:-1,1:-1] - g[:-2,1:-1] - g[2:,1:-1] - g[1:-1,:-2] - g[1:-1,2:]
    return std, float(lap.var())

def judge(row):
    aid, bk, ck = row
    try:
        g = fetch_gray(bk, ck)
        std, lap = metrics(g)
        return aid, (std < STD_MIN or lap < LAP_MIN), std, lap
    except Exception:
        return aid, None, None, None

for lib in LIBS:
    q = """SELECT a.asset_id, a.bucket, a.cos_key FROM dam_asset a
           WHERE a.lib=%s AND a.status='active' AND a.cos_key IS NOT NULL"""
    if LIMIT: q += f" LIMIT {LIMIT}"
    cur.execute(q, (lib,)); rows = cur.fetchall()
    print(f"[{lib}] 质检 {len(rows)} 张 (std<{STD_MIN} 或 lap<{LAP_MIN} 判废)", flush=True)
    rej = []; done = err = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for aid, bad, std, lap in ex.map(judge, rows):
            done += 1
            if bad is None: err += 1
            elif bad: rej.append(aid)
            if done % 3000 == 0:
                print(f"  [{lib}] {done}/{len(rows)}, 废 {len(rej)}, 取图失败 {err}", flush=True)
                if rej:
                    for s in range(0, len(rej), 5000):
                        cur.execute("UPDATE dam_asset SET status='reject' WHERE asset_id=ANY(%s)", (rej[s:s+5000],))
                    cn.commit(); rej = []
    if rej:
        cur.execute("UPDATE dam_asset SET status='reject' WHERE asset_id=ANY(%s)", (rej,)); cn.commit()
    print(f"[{lib}] 完成,判废(已隐藏),取图失败 {err}", flush=True)
print("DONE", flush=True)
cur.close(); cn.close()
