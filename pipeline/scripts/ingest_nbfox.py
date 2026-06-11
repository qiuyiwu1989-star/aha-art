#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nbfox(麦田艺术)来源适配器 → aha works/files。

nbfox 已有:图在 COS `artworks/nbfox/images/<slug>.jpg`,元数据在
`artworks/nbfox/nbfox_records.jsonl`(字段:slug/title中文/artist中文/artist_slug/
year/style画派/genre体裁/topics/image_cos…,作者99%·年代99%·风格98%完整)。

本适配器:读 jsonl → 与 images/ 实际对象比对 → 逐图并发算 sha256/phash+宽高 →
upsert artists / insert works(带中文元数据) / insert files。status=pending,
之后统一走 gate.py 闸门(去重+VLM标注+三路分流)。sha256 去重幂等。

用法: python3 ingest_nbfox.py [--limit N] [--workers 12]
"""
import os, sys, io, json, hashlib, argparse, time, threading, re
from concurrent.futures import ThreadPoolExecutor, as_completed

from qcloud_cos import CosConfig, CosS3Client
from PIL import Image
import imagehash
import psycopg2

Image.MAX_IMAGE_PIXELS = None
BUCKET = "aha-1254041526"
JSONL_KEY = "artworks/nbfox/nbfox_records.jsonl"
IMG_PREFIX = "artworks/nbfox/images/"
BATCH = "nbfox:maitian"

def _cfg(p): return json.load(open(os.path.expanduser(p)))
def cos_client():
    d = _cfg("~/.aha_cos.json")
    return CosS3Client(CosConfig(Region=d["region"], SecretId=d["secret_id"], SecretKey=d["secret_key"]))
def pg_conn():
    d = _cfg("~/.aha_pg.json")
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

CL = cos_client()
_tls = threading.local()
def cos():
    if not hasattr(_tls, "cl"): _tls.cl = cos_client()
    return _tls.cl
def conn():
    if not hasattr(_tls, "cn"): _tls.cn = pg_conn()
    return _tls.cn

def cos_key_of(rec):
    """从 image_cos URL 取 cos_key;缺失则按 slug 兜底。"""
    u = rec.get("image_cos") or ""
    m = re.search(r"\.myqcloud\.com/(.+)$", u)
    if m: return m.group(1)
    if rec.get("slug"): return f"{IMG_PREFIX}{rec['slug']}.jpg"
    return None

def list_existing_images():
    keys = set(); marker = ""
    while True:
        r = CL.list_objects(Bucket=BUCKET, Prefix=IMG_PREFIX, Marker=marker, MaxKeys=1000)
        cs = r.get("Contents", [])
        for x in cs:
            k = x["Key"]
            if not k.endswith("/"): keys.add(k)
        if r.get("IsTruncated") == "true" and cs: marker = cs[-1]["Key"]
        else: break
    return keys

def load_records():
    raw = CL.get_object(Bucket=BUCKET, Key=JSONL_KEY)["Body"].get_raw_stream().read()
    recs = []
    for ln in raw.decode("utf-8", "ignore").split("\n"):
        ln = ln.strip()
        if not ln: continue
        try: recs.append(json.loads(ln))
        except Exception: pass
    return recs

_STOP = {"van","von","der","den","del","della","di","de","la","le","el","dos","das","of","the"}
def deslug(slug):
    return " ".join(p if p in _STOP else p.capitalize() for p in (slug or "").split("-")) or None

def ingest_one(rec, cos_key):
    cn = conn(); cur = cn.cursor()
    try:
        raw = cos().get_object(Bucket=BUCKET, Key=cos_key)["Body"].get_raw_stream().read()
        sha = hashlib.sha256(raw).hexdigest()
        cur.execute("SELECT 1 FROM files WHERE sha256=%s LIMIT 1", (sha,))
        if cur.fetchone(): cn.commit(); return "dup"
        im = Image.open(io.BytesIO(raw)); im.load(); w, h = im.size
        ph = str(imagehash.phash(im.convert("RGB")))
        ext = (cos_key.rsplit(".", 1)[-1] or "jpg").lower()

        a_slug = rec.get("artist_slug") or "unknown"
        artist_id = "nbfox:" + a_slug
        name_cn = (rec.get("artist") or "").strip() or None
        cur.execute("INSERT INTO artists(artist_id,name_cn,name_en,created_at) VALUES(%s,%s,%s,now()) "
                    "ON CONFLICT (artist_id) DO NOTHING",
                    (artist_id, name_cn, deslug(a_slug)))
        cur.execute("INSERT INTO works(title,artist_id,year,school,source_batch,src_work_id) "
                    "VALUES(%s,%s,%s,%s,%s,%s) RETURNING work_id",
                    ((rec.get("title") or "").strip() or None, artist_id,
                     (rec.get("year") or None), (rec.get("style") or None),
                     BATCH, rec.get("slug")))
        work_id = cur.fetchone()[0]
        cur.execute("INSERT INTO files(work_id,cos_key,sha256,phash,width,height,bytes,fmt,source_batch,src_file_id,created_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (cos_key) DO NOTHING RETURNING file_id",
                    (work_id, cos_key, sha, ph, w, h, len(raw), ext, BATCH, rec.get("slug")))
        fid = cur.fetchone()
        if fid:
            cur.execute("UPDATE works SET primary_file_id=%s WHERE work_id=%s", (fid[0], work_id))
            # genre/topics 暂存进 works 没有列,挂到 src_work_id 已够溯源;体裁后续可入 vlm 对照
        cn.commit()
        return "ok"
    except Exception as e:
        cn.rollback()
        return f"bad:{repr(e)[:60]}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int); ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()

    print("列 COS 现有图片…")
    have = list_existing_images()
    print(f"  images/ 实际对象 {len(have)}")
    print("读 nbfox_records.jsonl…")
    recs = load_records()
    print(f"  记录 {len(recs)}")

    todo = []
    skip_noimg = 0
    for r in recs:
        k = cos_key_of(r)
        if not k or k not in have: skip_noimg += 1; continue
        todo.append((r, k))
    if a.limit: todo = todo[:a.limit]
    print(f"  可入库(图存在) {len(todo)}  缺图跳过 {skip_noimg}")

    n = {"ok": 0, "dup": 0, "bad": 0}; t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(ingest_one, r, k) for r, k in todo]
        for i, f in enumerate(as_completed(futs), 1):
            res = f.result()
            key = "ok" if res == "ok" else ("dup" if res == "dup" else "bad")
            n[key] += 1
            if key == "bad" and n["bad"] <= 10: print("  ", res)
            if i % 500 == 0:
                print(f"  {i}/{len(todo)}  ok={n['ok']} dup={n['dup']} bad={n['bad']}  {i/(time.time()-t0):.1f}/s")
    print(f"\n>>> nbfox 完成 ok={n['ok']} dup={n['dup']} bad={n['bad']}  用时{time.time()-t0:.0f}s  batch={BATCH}")

if __name__ == "__main__":
    main()
