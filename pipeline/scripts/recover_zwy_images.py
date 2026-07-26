#!/usr/bin/env python3
"""补拉造物云 COMPLETED 但无图片的记录。
从 zaowuyun API 获取执行详情 → 下载图片 → 上传 COS → 插入 gen_file。

用法:
  python3 recover_zwy_images.py [--workers 6] [--limit N] [--dry-run]
"""
import os, sys, json, io, time, hashlib, argparse, threading, urllib.request, ssl, socket
from concurrent.futures import ThreadPoolExecutor, as_completed
os.environ.setdefault('MODELSCOPE_CACHE', os.path.expanduser('~/.cache/modelscope'))
socket.setdefaulttimeout(60)
import imagehash
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED = True
Image.MAX_IMAGE_PIXELS = None
from qcloud_cos import CosS3Client, CosConfig
import psycopg2

# ── 配置 ──
API_BASE = "https://app.zaowuyun.com"
TOKEN = "sk-DYZfTj8acrqtOYmlMj4C8qSbgiAbcIHEuJCh17BbH2XQQlGJ"
BUCKET = "aha-1254041526"
COS_PREFIX = "artworks/_generated/zaowuyun/"
SOURCE = "zaowuyun_team"

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

def _cfg(p):
    return json.load(open(os.path.expanduser(p)))

_tls = threading.local()
def cos():
    if not hasattr(_tls, "cl"):
        c = _cfg("~/.aha_cos.json")
        _tls.cl = CosS3Client(CosConfig(Region=c["region"], SecretId=c["secret_id"], SecretKey=c["secret_key"], Timeout=30))
    return _tls.cl

def pg():
    d = _cfg("~/.aha_pg.json")
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

def api_detail(instance_id):
    req = urllib.request.Request(f"{API_BASE}/api/workflow/executions/{instance_id}",
                                headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=30, context=_SSL).read())
    return resp["data"]

def extract_output_images(detail):
    """从执行详情中提取输出图片 URL（兼容 data 和 file_list 两种格式）"""
    out = detail.get("output") or {}
    images = []
    if isinstance(out, dict):
        data_list = out.get("data", [])
        if isinstance(data_list, list):
            images.extend(u for u in data_list if isinstance(u, str) and "http" in u)
        file_list = out.get("file_list", [])
        if isinstance(file_list, list):
            images.extend(u for u in file_list if isinstance(u, str) and "http" in u)
    return list(dict.fromkeys(images))

def recover_one(instance_id, wf_name):
    """补拉单条记录的图片"""
    cn = pg()
    try:
        # 获取 API 详情
        detail = api_detail(instance_id)
        images = extract_output_images(detail)
        if not images:
            cn.close()
            return 0

        n_img = 0
        for url in images:
            try:
                # 下载图片
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                raw = urllib.request.urlopen(req, timeout=30, context=_SSL).read()
                sha = hashlib.sha256(raw).hexdigest()
                ext = url.rsplit(".", 1)[-1].split("?")[0].lower()
                if ext not in ("png", "jpg", "jpeg", "webp"): ext = "png"

                # 检查是否已存在
                cur = cn.cursor()
                cur.execute("SELECT cos_key FROM gen_file WHERE sha256=%s LIMIT 1", (sha,))
                if cur.fetchone():
                    cur.close()
                    n_img += 1
                    continue
                cur.close()

                # 获取图片信息
                im = Image.open(io.BytesIO(raw))
                im.load()
                w, h = im.size
                ph = str(imagehash.phash(im.convert("RGB")))

                # 上传 COS
                cos_key = f"{COS_PREFIX}{wf_name}/{sha}.{ext}"
                cos().put_object(Bucket=BUCKET, Key=cos_key, Body=raw)

                # 插入 gen_file
                cur = cn.cursor()
                cur.execute("""INSERT INTO gen_file (instance_id, cos_key, src_url, sha256, phash, width, height, bytes, fmt, role, source, q_status)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'output', %s, 'pending')
                               ON CONFLICT (cos_key) DO NOTHING""",
                            (instance_id, cos_key, url, sha, ph, w, h, len(raw), ext, SOURCE))
                cn.commit()
                cur.close()
                n_img += 1
            except Exception as e:
                pass  # 跳过单张图片失败

        cn.close()
        return n_img
    except Exception as e:
        try: cn.close()
        except: pass
        return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="最多处理 N 条，0=不限")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cn = pg()
    cur = cn.cursor()

    # 查找 COMPLETED 但无图片的记录
    cur.execute("""SELECT gr.instance_id, gr.workflow_name
                   FROM gen_run gr
                   LEFT JOIN gen_file gf ON gr.instance_id=gf.instance_id AND gf.role='output'
                   WHERE gr.source='zaowuyun_team' AND gr.status='COMPLETED' AND gf.instance_id IS NULL
                   ORDER BY gr.start_time DESC""")
    rows = cur.fetchall()
    cur.close()
    cn.close()
    print(f"COMPLETED 但无图片的记录: {len(rows)} 条")

    if a.limit:
        rows = rows[:a.limit]
        print(f"限制处理: {len(rows)} 条")

    if a.dry_run:
        wfs = {}
        for _, wf in rows:
            wfs[wf] = wfs.get(wf, 0) + 1
        print("\n按工作流分布:")
        for wf, cnt in sorted(wfs.items(), key=lambda x: -x[1]):
            print(f"  {wf}: {cnt}")
        return

    t0 = time.time()
    n_done = n_img = n_fail = 0

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {}
        for iid, wf in rows:
            futs[ex.submit(recover_one, iid, wf)] = (iid, wf)

        for fut in as_completed(futs):
            iid, wf = futs[fut]
            n_done += 1
            try:
                imgs = fut.result()
                n_img += imgs
                if imgs == 0:
                    n_fail += 1
            except Exception as e:
                n_fail += 1

            if n_done % 100 == 0:
                elapsed = time.time() - t0
                rate = n_done / elapsed if elapsed > 0 else 0
                eta = (len(rows) - n_done) / rate / 60 if rate > 0 else 0
                print(f"  {n_done}/{len(rows)} done, {n_img} imgs, {n_fail} fail, {rate:.1f}/s, ETA {eta:.0f}min", flush=True)

    elapsed = time.time() - t0
    print(f"\n完成! {n_done} 条, {n_img} 张图, {n_fail} 失败, 用时 {elapsed:.0f}s")

if __name__ == "__main__":
    main()
