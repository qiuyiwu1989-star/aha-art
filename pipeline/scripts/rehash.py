#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多哈希加强:为 files 回填 dhash + whash(已有 phash)。

phash(DCT)单一指纹易误并/漏并;加 dhash(差分,对渐变敏感)+ whash(小波,对结构敏感)
组成指纹集成,后续去重用「多数票」更稳(为 embedding ②之前的低风险加强)。
读 COS 图(缩到512算,与gate一致,scale-robust),幂等:只补 dhash 为空的。

用法: python3 rehash.py [--limit N] [--workers 12]
"""
import os, io, json, argparse, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from qcloud_cos import CosConfig, CosS3Client
from PIL import Image
import imagehash, psycopg2

Image.MAX_IMAGE_PIXELS = None
BUCKET = "aha-1254041526"

def _cfg(p): return json.load(open(os.path.expanduser(p)))
def cos_client():
    d = _cfg("~/.aha_cos.json")
    return CosS3Client(CosConfig(Region=d["region"], SecretId=d["secret_id"], SecretKey=d["secret_key"], Timeout=30))
def pg_conn():
    d = _cfg("~/.aha_pg.json")
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

_tls = threading.local()
def cos():
    if not hasattr(_tls, "cl"): _tls.cl = cos_client()
    return _tls.cl
def conn():
    if not hasattr(_tls, "cn"): _tls.cn = pg_conn()
    return _tls.cn

def do_one(row):
    fid, cos_key = row
    cn = conn(); cur = cn.cursor()
    try:
        raw = cos().get_object(Bucket=BUCKET, Key=cos_key)["Body"].get_raw_stream().read()
        im = Image.open(io.BytesIO(raw)); im.draft("RGB", (512, 512))
        im = im.convert("RGB"); im.thumbnail((512, 512))
        dh = str(imagehash.dhash(im)); wh = str(imagehash.whash(im))
        cur.execute("UPDATE files SET dhash=%s, whash=%s WHERE file_id=%s", (dh, wh, fid))
        cn.commit(); return "ok"
    except Exception as e:
        cn.rollback(); return f"bad:{repr(e)[:50]}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int); ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    cn = pg_conn(); cur = cn.cursor()
    q = "SELECT file_id, cos_key FROM files WHERE dhash IS NULL ORDER BY file_id"
    if a.limit: q += f" LIMIT {int(a.limit)}"
    cur.execute(q); rows = cur.fetchall()
    print(f"待回填 {len(rows)}  workers={a.workers}")
    n = {"ok": 0, "bad": 0}; t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(do_one, r) for r in rows]
        for i, f in enumerate(as_completed(futs), 1):
            res = f.result(); n["ok" if res == "ok" else "bad"] += 1
            if res != "ok" and n["bad"] <= 8: print("  ", res)
            if i % 1000 == 0: print(f"  {i}/{len(rows)}  ok={n['ok']} bad={n['bad']}  {i/(time.time()-t0):.0f}/s")
    print(f"\n>>> 完成 ok={n['ok']} bad={n['bad']}  用时{time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
