#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用 COS 前缀 → 统一向量底座(dam_asset + dam_embedding)入库 adapter。
把某个桶/前缀下的图登记成一个 lib,并算 CLIP ViT-B/32 向量。幂等(UNIQUE bucket,cos_key)。
加新库 = 跑一次本脚本 + 在 dam_api.py 的 LIBS 注册一行。

用法:
  python3 scan_cos_lib.py --bucket aha-1254041526 --prefix NewYearPaintings/ --lib nianhua --source nianhua-cos
"""
import os, io, json, argparse, urllib.request, ssl, socket, time
import numpy as np
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED = True
Image.MAX_IMAGE_PIXELS = 60_000_000   # 像素上限:超大图(国画/油画 tif 可达数GB)触发异常被跳过,防 OOM
import psycopg2
from qcloud_cos import CosConfig, CosS3Client

socket.setdefaulttimeout(18)
_SSL = ssl.create_default_context(); _SSL.check_hostname = False; _SSL.verify_mode = ssl.CERT_NONE
IMG_BASE = "https://aha.yishujia.art"   # /img/ 同源代理 COS 桶 aha-1254041526
IMG_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff', '.tif', '.avif')

def _cfg(p): return json.load(open(os.path.expanduser(p)))
def pg():
    d = _cfg("~/.aha_pg.json")
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])
def cos():
    d = _cfg("~/.aha_cos.json")
    return CosS3Client(CosConfig(Region=d['region'], SecretId=d['secret_id'], SecretKey=d['secret_key']))

import urllib.parse
AHA_BUCKET = "aha-1254041526"
def fetch_image(cos_key, thumb=None, bucket=None):
    qk = urllib.parse.quote(cos_key, safe='/')
    if bucket and bucket != AHA_BUCKET:   # 其它桶走 COS 公网直连
        url = f"https://{bucket}.cos.ap-shanghai.myqcloud.com/{qk}"
    else:                                  # aha 桶走内网 /img 代理(更快)
        url = f"{IMG_BASE}/img/{qk}"
    if thumb: url += f"?imageMogr2/thumbnail/{thumb}x"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=14, context=_SSL).read()
    return Image.open(io.BytesIO(raw)).convert("RGB")

def register(c, cn, bucket, prefix, lib, source):
    """列前缀对象 → 插 dam_asset(跳过已存在)。返回新登记数。"""
    cur = cn.cursor(); marker = ''; seen = 0; added = 0
    while True:
        r = c.list_objects(Bucket=bucket, Prefix=prefix, Marker=marker, MaxKeys=1000)
        for o in r.get('Contents', []):
            k = o['Key']
            if k.endswith('/') or not k.lower().endswith(IMG_EXT):
                continue
            seen += 1
            fmt = k.rsplit('.', 1)[-1].lower()
            cur.execute("""INSERT INTO dam_asset (bucket,cos_key,lib,source,bytes,fmt,created_ts,status,indexed_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,'active',now())
                           ON CONFLICT (bucket,cos_key) DO NOTHING""",
                        (bucket, k, lib, source, int(o.get('Size', 0)), fmt, o.get('LastModified')))
            added += cur.rowcount
        cn.commit()
        if r.get('IsTruncated') == 'true':
            marker = r['NextMarker']
        else:
            break
    cur.close()
    print(f"登记: 前缀图像 {seen} 张,新增 {added} 条(其余已存在)", flush=True)
    return added

def encode(cn, lib, batch, workers):
    """对该 lib 下还没向量的资产算 CLIP,并补 width/height。"""
    cur = cn.cursor()
    cur.execute("""SELECT a.asset_id, a.cos_key, a.bucket FROM dam_asset a
                   LEFT JOIN dam_embedding e USING(asset_id)
                   WHERE a.lib=%s AND e.asset_id IS NULL""", (lib,))
    rows = cur.fetchall()
    print(f"待编码: {len(rows)} 张", flush=True)
    if not rows:
        cur.close(); return
    import torch, clip
    from concurrent.futures import ThreadPoolExecutor
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading CLIP ViT-B/32 on {device}...", flush=True)
    model, preprocess = clip.load("ViT-B/32", device=device); model.eval()

    def fetch_one(row):
        aid, cos_key, bucket = row
        try:
            img = fetch_image(cos_key, 384, bucket)   # 只取 384 缩略图;失败即跳过(超大手卷原图会拖死/OOM)
            return aid, preprocess(img), img.size
        except Exception as e:
            return aid, e, None

    n_done = n_err = 0
    pool = ThreadPoolExecutor(max_workers=workers)
    for i in range(0, len(rows), batch):
        chunk = rows[i:i+batch]
        tensors, ids, sizes = [], [], {}
        for aid, res, sz in pool.map(fetch_one, chunk):
            if isinstance(res, Exception):
                n_err += 1
                if n_err <= 3: print(f"  ERROR {aid}: {str(res)[:80]}", flush=True)
                continue
            tensors.append(res); ids.append(aid); sizes[aid] = sz
        if not tensors: continue
        with torch.no_grad():
            bt = torch.stack(tensors).to(device)
            emb = model.encode_image(bt); emb = emb / emb.norm(dim=-1, keepdim=True)
        for j, aid in enumerate(ids):
            arr = emb[j].cpu().numpy().astype(np.float32)
            vec_str = '[' + ','.join(f'{v:.6f}' for v in arr) + ']'
            cur.execute("INSERT INTO dam_embedding (asset_id,model,embedding) VALUES (%s,'clip-vit-b32',%s::vector) ON CONFLICT (asset_id) DO NOTHING", (aid, vec_str))
            if sizes.get(aid):
                cur.execute("UPDATE dam_asset SET width=%s,height=%s WHERE asset_id=%s", (sizes[aid][0], sizes[aid][1], aid))
        cn.commit(); n_done += len(ids)
        if n_done % 200 == 0: print(f"  {n_done}/{len(rows)} done, {n_err} err", flush=True)
    cur.close()
    print(f"编码完成: {n_done} 张, {n_err} 错误", flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default="aha-1254041526")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--lib", required=True)
    ap.add_argument("--source", default="")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--register-only", action="store_true")
    ap.add_argument("--encode-only", action="store_true", help="跳过登记,只对该 lib 现有无向量资产编码")
    a = ap.parse_args()
    cn = pg()
    if not a.encode_only:
        if not a.source:
            ap.error("登记需要 --source(--prefix 为空表示整桶)")
        print(f"[{time.strftime('%H:%M:%S')}] 扫 {a.bucket}/{a.prefix} → lib={a.lib}", flush=True)
        register(cos(), cn, a.bucket, a.prefix, a.lib, a.source)
    if not a.register_only:
        encode(cn, a.lib, a.batch, a.workers)
    cn.close()
    print(f"[{time.strftime('%H:%M:%S')}] DONE", flush=True)

if __name__ == "__main__":
    main()
