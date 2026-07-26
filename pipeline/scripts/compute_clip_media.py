#!/usr/bin/env python3
"""给造物云【素材库】zaowuyun_media 计算 CLIP embedding,用于语义检索/以图搜图。

和 compute_clip.py(生成区 gen_clip)对称,但这里是扁平表:向量直接存
zaowuyun_media.embedding_vec(vector(512))。查询端在 dam_api.py 必须同样用
ViT-B/32 对齐(素材入库时的自动分类用的是另一个模型,不能拿来当检索向量)。

用法: python3 compute_clip_media.py [--batch 32] [--limit N] [--workers 8]
"""
import os, json, io, argparse, urllib.request, ssl, socket
import numpy as np
import torch
import clip
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED = True
Image.MAX_IMAGE_PIXELS = None  # 素材里有上亿像素大图,关掉 PIL 解压炸弹保护
import psycopg2

socket.setdefaulttimeout(30)
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

IMG_BASE = "https://aha.yishujia.art"   # /img/ 同源代理 COS 桶 aha-1254041526

def _cfg(p): return json.load(open(os.path.expanduser(p)))

def pg():
    d = _cfg("~/.aha_pg.json")
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

def fetch_image(cos_key, thumb=None):
    url = f"{IMG_BASE}/img/{cos_key}"
    if thumb:
        url += f"?imageMogr2/thumbnail/{thumb}x"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=20, context=_SSL).read()
    return Image.open(io.BytesIO(raw)).convert("RGB")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    cn = pg()
    cur = cn.cursor()
    # 确保向量列存在(幂等)
    cur.execute("ALTER TABLE zaowuyun_media ADD COLUMN IF NOT EXISTS embedding_vec vector(512)")
    cn.commit()

    cur.execute("""SELECT src_id, cos_key FROM zaowuyun_media
                   WHERE status='stored' AND cos_key IS NOT NULL AND embedding_vec IS NULL
                   ORDER BY imported_at DESC""")
    rows = cur.fetchall()
    print(f"待计算: {len(rows)} 张", flush=True)
    if not rows:
        print("无待办,跳过(不加载模型)。", flush=True)
        cur.close(); cn.close(); return
    if a.limit:
        rows = rows[:a.limit]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading CLIP ViT-B/32 on {device}...", flush=True)
    model, preprocess = clip.load("ViT-B/32", device=device)
    model.eval()

    from concurrent.futures import ThreadPoolExecutor

    def fetch_one(row):
        sid, cos_key = row
        try:
            try:
                img = fetch_image(cos_key, 384)   # 优先 384 缩略图(CLIP 缩到 224),省带宽
            except Exception:
                img = fetch_image(cos_key)        # 超大图缩略图可能 400,回退原图
            return sid, preprocess(img)
        except Exception as e:
            return sid, e

    n_done = n_err = 0
    pool = ThreadPoolExecutor(max_workers=a.workers)
    for i in range(0, len(rows), a.batch):
        batch = rows[i:i+a.batch]
        images, ids = [], []
        for sid, res in pool.map(fetch_one, batch):
            if isinstance(res, Exception):
                n_err += 1
                if n_err <= 3:
                    print(f"  ERROR {sid}: {str(res)[:80]}", flush=True)
                continue
            images.append(res); ids.append(sid)
        if not images:
            continue
        with torch.no_grad():
            bt = torch.stack(images).to(device)
            emb = model.encode_image(bt)
            emb = emb / emb.norm(dim=-1, keepdim=True)
        for j, sid in enumerate(ids):
            arr = emb[j].cpu().numpy().astype(np.float32)
            vec_str = '[' + ','.join(f'{v:.6f}' for v in arr) + ']'
            cur.execute("UPDATE zaowuyun_media SET embedding_vec=%s::vector WHERE src_id=%s", (vec_str, sid))
        cn.commit()
        n_done += len(ids)
        if n_done % 200 == 0:
            print(f"  {n_done}/{len(rows)} done, {n_err} errors", flush=True)

    print(f"\n完成! {n_done} 张, {n_err} 错误", flush=True)
    cur.close(); cn.close()

if __name__ == "__main__":
    main()
