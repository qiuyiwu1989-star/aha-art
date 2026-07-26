#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给超大原图(>32MB,imageMogr2处理不了→前端裂)预生成缩略图存 COS artworks/_thumb/{file_id}.jpg。
PIL draft 模式快速降采样(专治超大JPEG,省内存)。映射记 file_thumb 表,catalog_api 启动加载后 img_url 自动用。
用法: python3 gen_thumbs.py [--exhibited-only] [--limit N]"""
import os, io, json, argparse, psycopg2
from psycopg2.extras import execute_values
from qcloud_cos import CosConfig, CosS3Client
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
BK = "aha-1254041526"; MAXSIDE = 1600

d = json.load(open('/home/ubuntu/.aha_cos.json'))
C = CosS3Client(CosConfig(Region=d['region'], SecretId=d['secret_id'], SecretKey=d['secret_key']))
pg = json.load(open('/home/ubuntu/.aha_pg.json'))
con = psycopg2.connect(host=pg['host'], port=pg['port'], dbname=pg['dbname'], user=pg['user'], password=pg['password']); cur = con.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS file_thumb(file_id bigint PRIMARY KEY, orig_key text, thumb_key text, made_at timestamptz DEFAULT now())""")
con.commit()

ap = argparse.ArgumentParser()
ap.add_argument("--exhibited-only", action="store_true"); ap.add_argument("--limit", type=int)
a = ap.parse_args()
# imageMogr2 拒处理: >32MB 或 总像素>2.5亿 或 任一边>30000px
where = "(f.bytes>33554432 OR f.width::bigint*f.height>250000000 OR f.width>30000 OR f.height>30000) AND ft.file_id IS NULL"
if a.exhibited_only: where += " AND w.exhibited"
sql = f"""SELECT f.file_id, f.cos_key FROM files f JOIN works w ON w.work_id=f.work_id
          LEFT JOIN file_thumb ft ON ft.file_id=f.file_id WHERE {where} ORDER BY w.exhibited DESC, f.bytes"""
if a.limit: sql += f" LIMIT {a.limit}"
cur.execute(sql); rows = cur.fetchall()
print(f"待生成缩略图 {len(rows)} 张", flush=True)

ok = bad = 0; done = []
for i, (fid, key) in enumerate(rows, 1):
    try:
        raw = C.get_object(Bucket=BK, Key=key)["Body"].get_raw_stream().read()
        im = Image.open(io.BytesIO(raw))
        im.draft('RGB', (MAXSIDE, MAXSIDE))          # 超大JPEG解码即降采样,快
        im = im.convert('RGB'); im.thumbnail((MAXSIDE, MAXSIDE))
        buf = io.BytesIO(); im.save(buf, 'JPEG', quality=82); buf.seek(0)
        tkey = f"artworks/_thumb/{fid}.jpg"
        C.put_object(Bucket=BK, Key=tkey, Body=buf, ContentType='image/jpeg')
        done.append((fid, key, tkey)); ok += 1
    except Exception as e:
        bad += 1; print(f"  ✗ {key.split('/')[-1]}: {str(e)[:50]}", flush=True)
    if i % 20 == 0:
        execute_values(cur, "INSERT INTO file_thumb(file_id,orig_key,thumb_key) VALUES %s ON CONFLICT(file_id) DO NOTHING", done)
        con.commit(); done = []
        print(f"  {i}/{len(rows)} ok={ok} bad={bad}", flush=True)
if done:
    execute_values(cur, "INSERT INTO file_thumb(file_id,orig_key,thumb_key) VALUES %s ON CONFLICT(file_id) DO NOTHING", done)
    con.commit()
print(f"\n完成 ok={ok} bad={bad}  缩略图存 artworks/_thumb/", flush=True)
