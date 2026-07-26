#!/usr/bin/env python3
"""计算造物云图片的 CLIP embedding，用于语义检索。
用法: python3 compute_clip.py [--batch 32] [--limit N]
"""
import os, json, io, argparse, urllib.request, ssl, socket
import numpy as np
import torch
import clip
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED = True
Image.MAX_IMAGE_PIXELS = None  # 关掉 PIL 解压炸弹保护(素材里有 2 亿像素的大图)
import psycopg2

socket.setdefaulttimeout(30)
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

def _cfg(p): return json.load(open(os.path.expanduser(p)))

def pg():
    d = _cfg("~/.aha_pg.json")
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

def fetch_image(url):
    if url.startswith("/"):
        url = "https://aha.yishujia.art" + url
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=15, context=_SSL).read()
    return Image.open(io.BytesIO(raw)).convert("RGB")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)  # 并发取图线程数
    a = ap.parse_args()

    # 加载 CLIP 模型
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading CLIP model on {device}...")
    model, preprocess = clip.load("ViT-B/32", device=device)
    model.eval()

    cn = pg()
    cur = cn.cursor()

    # 找出还没有 embedding 的图片
    cur.execute("""SELECT gf.instance_id, gf.cos_key
                   FROM gen_file gf
                   LEFT JOIN gen_clip ce ON ce.instance_id=gf.instance_id
                   WHERE gf.source='zaowuyun_team' AND gf.role='output'
                   AND ce.instance_id IS NULL
                   ORDER BY gf.created_at DESC""")
    rows = cur.fetchall()
    print(f"待计算: {len(rows)} 张")

    if a.limit:
        rows = rows[:a.limit]

    import sys
    sys.path.insert(0, "/home/ubuntu/users/qiuyiwu/aha-art/pipeline")
    from catalog_api import img_url

    from concurrent.futures import ThreadPoolExecutor

    def fetch_one(row):
        iid, cos_key = row
        try:
            try:
                img = fetch_image(img_url(cos_key, 384))  # 优先 384px 缩略图(CLIP 会缩到 224),省带宽
            except Exception:
                img = fetch_image(img_url(cos_key))       # 超大图 COS 缩略图会 400,回退原图(已关像素上限)
            return iid, preprocess(img)
        except Exception as e:
            return iid, e

    n_done = n_err = 0
    pool = ThreadPoolExecutor(max_workers=a.workers)
    for i in range(0, len(rows), a.batch):
        batch = rows[i:i+a.batch]
        images = []
        ids = []

        # 并发取图(网络是瓶颈),CPU 编码仍按批
        for iid, res in pool.map(fetch_one, batch):
            if isinstance(res, Exception):
                n_err += 1
                if n_err <= 3:
                    print(f"  ERROR: {iid}: {str(res)[:80]}", flush=True)
                continue
            images.append(res)
            ids.append(iid)

        if not images:
            continue

        # 批量计算 embedding
        with torch.no_grad():
            batch_tensor = torch.stack(images).to(device)
            embeddings = model.encode_image(batch_tensor)
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)

        # 写入数据库(同时写 bytea embedding 与 pgvector embedding_vec;后者是语义检索实际查询的列)
        for j, iid in enumerate(ids):
            arr = embeddings[j].cpu().numpy().astype(np.float32)
            emb_bytes = arr.tobytes()
            vec_str = '[' + ','.join(f'{v:.6f}' for v in arr) + ']'
            cur.execute("""INSERT INTO gen_clip (instance_id, embedding, embedding_vec)
                           VALUES (%s, %s, %s::vector)
                           ON CONFLICT (instance_id) DO UPDATE
                             SET embedding=EXCLUDED.embedding, embedding_vec=EXCLUDED.embedding_vec""",
                        (iid, emb_bytes, vec_str))

        cn.commit()
        n_done += len(ids)
        if n_done % 100 == 0:
            print(f"  {n_done}/{len(rows)} done, {n_err} errors", flush=True)

    print(f"\n完成! {n_done} 张, {n_err} 错误")
    cur.close()
    cn.close()

if __name__ == "__main__":
    main()
