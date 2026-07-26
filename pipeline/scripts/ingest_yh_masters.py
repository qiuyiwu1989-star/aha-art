#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""世界大师油画全集 来源适配器 → aha works/files。

油画数据集的第二个文件夹 `artworks/油画数据集/2.世界大师油画全集/`(yh 之外、之前没灌)。
无配套 SQL,元数据全在路径里:<流派>/<艺术家>/.../<文件名>。约 5,493 张真图(另 ~5,528 个
`._` macOS 元数据垃圾文件需剔除)。

处理策略:
  1. 列 COS key,跳过 `._` 垃圾 + 非图;`--clean-junk` 可直接从 COS 删掉这些 `._` 文件。
  2. 路径解析元数据:流派=第1层目录(去水印后缀);艺术家=形如 `D德加`/`F鲁本斯` 的目录段
     (去拼音首字母前缀 + 分批保存/TIF 标记);标题=文件名清洗(去 淘宝/素材店/N幅 水印)。
  3. 图已在 COS,不重传——直接注册 files 指向现有 cos_key。
  4. 去重:逐图算 sha256,命中 files.sha256 即跳过(精确重复);phash 入库,灌完跑 xdedup.py
     做全库跨源近重复(大师名作多源易撞,届时标 dup)。
  5. 分辨率闸:min-side < 600 直接跳过(全局标准,与 gate 一致)。
  6. status=pending → 之后走 gate VLM 评估。

用法:
  python3 ingest_yh_masters.py --clean-junk           # 先删 COS 里的 ._ 垃圾文件
  python3 ingest_yh_masters.py --theme 印象派 --limit 50   # 试点一个流派
  python3 ingest_yh_masters.py                          # 全量灌(幂等,可重跑增量)
"""
import os, sys, io, re, json, hashlib, argparse, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from qcloud_cos import CosConfig, CosS3Client
from PIL import Image
import imagehash
import psycopg2

Image.MAX_IMAGE_PIXELS = None
BUCKET = "aha-1254041526"
BASE = "artworks/油画数据集/2.世界大师油画全集/"
BATCH = "yh:世界大师油画全集"
MIN_SIDE = int(os.environ.get("AHA_MIN_SIDE", "600"))
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")

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

# ---------- 元数据启发式 ----------
THEME_MAP = [
    ("巴洛克洛可可", "巴洛克与洛可可"), ("文艺复兴", "文艺复兴"), ("印象派", "印象派"),
    ("新古典主义浪漫主义写实主义", "新古典/浪漫/写实主义"), ("现代后现代", "现代与后现代"),
    ("西方精选", "西方精选"), ("星空", "后印象派"),
]
def norm_theme(seg):
    for k, v in THEME_MAP:
        if k in seg: return v
    return re.sub(r"[-—].*$", "", seg).replace("时期", "").replace("合集", "").strip() or None

# 艺术家目录段:拼音首字母 + 中文名,如 D德加 / F鲁本斯 / B毕沙罗 / G高更
ART_RE = re.compile(r"^[A-Z]([一-鿿·]{1,12})")
PERIOD_HINT = re.compile(r"\d{3,4}|世纪|时期|开端|盛期|之间|战争|艺术$|合集|全集|精选|缩略图|分批保存$")
def parse_artist(parts_mid):
    """从中间路径段里找艺术家(形如 D德加)。返回 name_cn 或 None。"""
    for seg in parts_mid:
        m = ART_RE.match(seg)
        if m:
            nm = m.group(1)
            nm = re.sub(r"[-—].*$", "", nm).strip("·").strip()
            if nm and not PERIOD_HINT.search(nm):
                return nm
    return None

WM = re.compile(r"[-_]?(淘宝|名画资源店|过客素材屋|素材资料.*?幅|高清图片素材.*|素材库|更多美术资源|更多.*资源|JPG|TIF|分批保存\d*|缩略图)[-_]?", re.I)
def clean_title(fn):
    t = re.sub(r"\.(jpe?g|png|webp|bmp|tiff?)$", "", fn, flags=re.I)
    t = WM.sub(" ", t)
    t = re.sub(r"[-_]{2,}", " ", t).strip(" -_·")
    t = re.sub(r"^\d+\s*", "", t)            # 去前导编号
    return t or "无题"

def slug(name):
    return re.sub(r"\s+", "", name)[:40] if name else "unknown"

# ---------- 列 COS ----------
def list_keys(prefix):
    keys, junk, marker, cl = [], [], "", cos_client()
    while True:
        rr = cl.list_objects(Bucket=BUCKET, Prefix=prefix, Marker=marker, MaxKeys=1000)
        cs = rr.get("Contents", [])
        for x in cs:
            k = x["Key"]
            if k.endswith("/"): continue
            fn = k.rsplit("/", 1)[-1]
            if fn.startswith("._"):           # macOS AppleDouble 垃圾
                junk.append(k); continue
            if k.lower().endswith(IMG_EXT): keys.append(k)
        if rr.get("IsTruncated") == "true" and cs: marker = cs[-1]["Key"]
        else: break
    return keys, junk

def clean_junk(keys):
    cl = cos_client(); n = 0
    for i in range(0, len(keys), 1000):
        chunk = keys[i:i + 1000]
        cl.delete_objects(Bucket=BUCKET, Delete={"Object": [{"Key": k} for k in chunk], "Quiet": "true"})
        n += len(chunk)
        print(f"  已删 {n}/{len(keys)} 个 ._ 垃圾")
    return n

# ---------- 灌单图 ----------
def ingest_one(key):
    cn = conn(); cur = cn.cursor()
    try:
        rel = key[len(BASE):]
        parts = rel.split("/")
        theme = norm_theme(parts[0]) if parts else None
        artist = parse_artist(parts[1:-1])
        title = clean_title(parts[-1])
        aid = "yhm:" + (slug(artist) if artist else "unknown")

        raw = cos().get_object(Bucket=BUCKET, Key=key)["Body"].get_raw_stream().read()
        sha = hashlib.sha256(raw).hexdigest()
        cur.execute("SELECT 1 FROM files WHERE sha256=%s LIMIT 1", (sha,))
        if cur.fetchone(): cn.commit(); return "dup"
        try:
            im = Image.open(io.BytesIO(raw)); w, h = im.size
        except Exception:
            cn.commit(); return "badimg"
        if min(w, h) < MIN_SIDE: cn.commit(); return "small"
        im.draft("RGB", (512, 512)); im = im.convert("RGB"); im.thumbnail((512, 512))
        ph = str(imagehash.phash(im))

        cur.execute("""INSERT INTO artists(artist_id,name_cn,created_at) VALUES(%s,%s,now())
                       ON CONFLICT (artist_id) DO NOTHING""",
                    (aid, artist or "佚名·待考"))
        cur.execute("""INSERT INTO works(title,artist_id,school,source_batch,src_work_id)
                       VALUES(%s,%s,%s,%s,%s) RETURNING work_id""",
                    (title, aid, theme, BATCH, rel))
        work_id = cur.fetchone()[0]
        cur.execute("""INSERT INTO files(work_id,cos_key,sha256,phash,width,height,bytes,fmt,source_batch,src_file_id,created_at)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (cos_key) DO NOTHING RETURNING file_id""",
                    (work_id, key, sha, ph, w, h, len(raw), key.rsplit(".", 1)[-1].lower(), BATCH, rel))
        fid = cur.fetchone()
        if fid: cur.execute("UPDATE works SET primary_file_id=%s WHERE work_id=%s", (fid[0], work_id))
        cn.commit()
        return "ok"
    except Exception as e:
        cn.rollback(); return f"bad:{repr(e)[:60]}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default=None, help="只灌某流派子目录(试点)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--clean-junk", action="store_true", help="从 COS 直接删除 ._ 垃圾文件")
    ap.add_argument("--dry-run", action="store_true", help="只解析元数据不入库")
    a = ap.parse_args()
    prefix = BASE + (a.theme + "/" if a.theme else "")
    print(f"列 COS {prefix} …")
    keys, junk = list_keys(prefix)
    print(f"真实图 {len(keys)}，._垃圾 {len(junk)}")

    if a.clean_junk and junk:
        print("删除 ._ 垃圾文件…"); clean_junk(junk); print("done")

    if a.limit: keys = keys[:a.limit]
    if a.dry_run:
        from collections import Counter
        th = Counter(); ar = Counter(); n_art = 0
        for k in keys:
            parts = k[len(BASE):].split("/")
            t = norm_theme(parts[0]); aa = parse_artist(parts[1:-1])
            th[t] += 1; ar[aa or "—未知—"] += 1
            if aa: n_art += 1
            if a.limit and a.limit <= 20:
                print(f"  流派={t} 艺术家={aa} 标题={clean_title(parts[-1])}")
        print(f"\n能抽到艺术家的: {n_art}/{len(keys)} ({n_art*100//max(1,len(keys))}%)")
        print("流派分布:", dict(th))
        print("艺术家 Top15:", ar.most_common(15))
        return

    t0 = time.time(); stat = {}
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(ingest_one, k) for k in keys]
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result(); key = r.split(":")[0]
            stat[key] = stat.get(key, 0) + 1
            if i % 100 == 0:
                sp = i / (time.time() - t0)
                print(f"  {i}/{len(keys)}  {sp:.1f}/s  {stat}")
    print(f"\n完成 {len(keys)} 张,用时 {int(time.time()-t0)}s:{stat}")
    print("提示:接着跑 `python3 xdedup.py` 做全库跨源近重复去重(标 dup),再 gate 过闸。")

if __name__ == "__main__":
    main()
