#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yishujia(AI产品名画库)来源适配器 → aha works/files。

数据=用户历史标注 jsonl(.daymug-uploads 解出),每条 {id, url(阿里云OSS图), 最终的文本(融合长标注)}。
**无艺术家/标题元数据**,只有图+一段 fused 标注。
本适配器:逐条从阿里云 url 下载图 → sha256 去重 → phash/宽高 → 传 COS artworks/yishujia/<id>.jpg
→ 写 works(artist=yishujia:unknown 占位, title 空) / files;**导入标注存 works.anno_import,
并种入 vlm.fused 立即可显**;status=pending(之后走 gate 补结构化V2+策展分类="也要调用")。
sha256 去重:与已入库的 ~13% 重合会自动跳过。

用法: python3 ingest_yishujia.py [--jsonl PATH] [--limit N] [--workers 12]
"""
import os, io, json, hashlib, argparse, time, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from qcloud_cos import CosConfig, CosS3Client
from PIL import Image
import imagehash, psycopg2
from psycopg2.extras import Json

Image.MAX_IMAGE_PIXELS = None
BUCKET = "aha-1254041526"
DEST_PREFIX = "artworks/yishujia/"
BATCH = "yishujia:art"
ARTIST_ID = "yishujia:unknown"
DEFAULT_JSONL = "/tmp/anno_peek/1780891660047-8h857TzJcbunH1PlybfJT.jsonl"

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

def ingest_one(rec):
    cn = conn(); cur = cn.cursor()
    rid = rec.get("id"); url = rec.get("url"); anno = (rec.get("最终的文本") or "").strip()
    if not rid or not url: return "bad"
    try:
        raw = urllib.request.urlopen(url, timeout=30).read()
        sha = hashlib.sha256(raw).hexdigest()
        cur.execute("SELECT 1 FROM files WHERE sha256=%s LIMIT 1", (sha,))
        if cur.fetchone(): cn.commit(); return "dup"
        im = Image.open(io.BytesIO(raw)); w, h = im.size
        im.draft("RGB", (512, 512)); im = im.convert("RGB"); im.thumbnail((512, 512))
        ph = str(imagehash.phash(im))
        ext = (url.rsplit(".", 1)[-1].split("?")[0] or "jpg").lower()
        if ext not in ("jpg", "jpeg", "png", "webp"): ext = "jpg"
        cos_key = f"{DEST_PREFIX}{rid}.{ext}"
        cos().put_object(Bucket=BUCKET, Key=cos_key, Body=raw,
                         ContentType=f"image/{'jpeg' if ext in ('jpg','jpeg') else ext}")
        # 导入标注:存 anno_import,并种入 vlm.fused 立即可显(gate 之后会用完整 V2 覆盖 vlm,anno_import 留底)
        vlm_seed = Json({"fused": anno, "_src": "yishujia_import"}) if anno else None
        cur.execute("""INSERT INTO works(title,artist_id,source_batch,src_work_id,anno_import,vlm)
                       VALUES(%s,%s,%s,%s,%s,%s) RETURNING work_id""",
                    (None, ARTIST_ID, BATCH, rid, anno or None, vlm_seed))
        work_id = cur.fetchone()[0]
        cur.execute("""INSERT INTO files(work_id,cos_key,sha256,phash,width,height,bytes,fmt,source_batch,src_file_id,created_at)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (cos_key) DO NOTHING RETURNING file_id""",
                    (work_id, cos_key, sha, ph, w, h, len(raw), ext, BATCH, rid))
        fid = cur.fetchone()
        if fid: cur.execute("UPDATE works SET primary_file_id=%s WHERE work_id=%s", (fid[0], work_id))
        cn.commit()
        return "ok"
    except Exception as e:
        cn.rollback()
        return f"bad:{repr(e)[:50]}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default=DEFAULT_JSONL)
    ap.add_argument("--limit", type=int); ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    recs = [json.loads(l) for l in open(a.jsonl, encoding="utf-8") if l.strip()]
    if a.limit: recs = recs[:a.limit]
    print(f"yishujia 记录 {len(recs)}  workers={a.workers}")
    n = {"ok": 0, "dup": 0, "bad": 0}; t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(ingest_one, r) for r in recs]
        for i, f in enumerate(as_completed(futs), 1):
            res = f.result(); k = res if res in ("ok", "dup") else "bad"
            n[k] += 1
            if k == "bad" and n["bad"] <= 8: print("  ", res)
            if i % 500 == 0: print(f"  {i}/{len(recs)}  ok={n['ok']} dup={n['dup']} bad={n['bad']}  {i/(time.time()-t0):.1f}/s")
    print(f"\n>>> yishujia 完成 ok={n['ok']} dup={n['dup']} bad={n['bad']}  用时{time.time()-t0:.0f}s  batch={BATCH}")

if __name__ == "__main__":
    main()
