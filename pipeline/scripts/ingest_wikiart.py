#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WikiArt 数据集 → aha Postgres 首次灌库（流式,不下载整包）。

进料口 = COS 上的 wikiart/WikiArt.zip（套娃:外层每个条目是一个画派 zip,STORED 未压缩;
内层 <画派>/<艺术家slug>/<标题slug>.jpg）。用 COS Range 把 zip 当可 seek 文件远程读,
逐图处理:sha256/phash 去重 → 传 artworks/wikiart/... → 写 artists/works/files。

用法:
  python3 ingest_wikiart.py --list                 # 列出 WikiArt.zip 内全部画派
  python3 ingest_wikiart.py --style neoclassicism  # 灌单个画派（试点）
  python3 ingest_wikiart.py --all                  # 灌 WikiArt.zip 全部画派
  附加: --limit N（每画派只处理前 N 幅,调试）  --dry-run（只统计,不传不写）
"""
import os, sys, io, json, struct, hashlib, argparse, time, zipfile, re

from qcloud_cos import CosConfig, CosS3Client
from PIL import Image
import imagehash
import psycopg2
from psycopg2.extras import execute_values

Image.MAX_IMAGE_PIXELS = None  # WikiArt 有大图,关掉 decompression bomb 警告上限

SRC_BUCKET = "aha-1254041526"           # 画作桶(cos.json 里 bucket 字段是错的,这里硬编码)
SRC_KEY    = "wikiart/WikiArt.zip"       # 套娃进料口
DEST_PREFIX = "artworks/wikiart/"        # 拆出来的单图存这里
MIN_SIDE = int(os.environ.get('AHA_MIN_SIDE', '600'))  # 短边 < 此值=低分辨率,一律不入库(全局标准,以后都不要)

# ---------- 凭据 ----------
def cos_client():
    d = json.load(open(os.path.expanduser("~/.aha_cos.json")))
    return CosS3Client(CosConfig(Region=d["region"], SecretId=d["secret_id"], SecretKey=d["secret_key"]))

def pg_conn():
    d = json.load(open(os.path.expanduser("~/.aha_pg.json")))
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"],
                            user=d["user"], password=d["password"])

CL = cos_client()

# ---------- COS 可 seek 文件(支持子区间) ----------
class COSFile(io.RawIOBase):
    def __init__(self, key, base=0, length=None):
        self.key = key; self.base = base; self.pos = 0
        if length is None:
            length = int(CL.head_object(Bucket=SRC_BUCKET, Key=key)["Content-Length"])
        self.size = length
    def seekable(self): return True
    def readable(self): return True
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos
    def tell(self): return self.pos
    def read(self, n=-1):
        if n is None or n < 0: n = self.size - self.pos
        if n <= 0 or self.pos >= self.size: return b""
        n = min(n, self.size - self.pos)
        a = self.base + self.pos; b = a + n - 1
        data = CL.get_object(Bucket=SRC_BUCKET, Key=self.key,
                             Range=f"bytes={a}-{b}")["Body"].get_raw_stream().read()
        self.pos += len(data)
        return data

def inner_zip(outer, style_filename):
    """把外层 WikiArt.zip 里某个 STORED 画派 zip 切成独立可 seek 视图。"""
    zi = outer.getinfo(style_filename)
    assert zi.compress_type == 0, f"{style_filename} 非 STORED,需改用解压"
    f = outer.fp  # 复用底层 COSFile
    f.seek(zi.header_offset); lh = f.read(30)
    n, m = struct.unpack("<HH", lh[26:30])
    data_start = zi.header_offset + 30 + n + m
    sub = COSFile(SRC_KEY, base=data_start, length=zi.compress_size)
    return zipfile.ZipFile(sub)

# ---------- slug 反转为可读 ----------
_STOP = {"van","von","der","den","del","della","di","de","la","le","el","dos","das","of","the"}
def deslug_name(slug):
    parts = slug.split("-")
    return " ".join(p if p in _STOP else p.capitalize() for p in parts)
def deslug_title(slug):
    slug = re.sub(r"-(\d{3,4})$", r" (\1)", slug)   # 末尾年份括起来
    parts = slug.split("-")
    out = " ".join(p for p in parts)
    return out[:1].upper() + out[1:] if out else out

# ---------- 主流程 ----------
def list_styles():
    z = zipfile.ZipFile(COSFile(SRC_KEY))
    return [zi.filename for zi in z.infolist() if zi.filename.endswith(".zip")]

def style_name(style_filename):
    return style_filename.split("/")[-1][:-4]   # WikiArt/neoclassicism.zip -> neoclassicism

def ingest_style(style_filename, batch_id, conn, limit=None, dry=False):
    style = style_name(style_filename)
    outer = zipfile.ZipFile(COSFile(SRC_KEY))
    iz = inner_zip(outer, style_filename)
    names = [n for n in iz.namelist() if not n.endswith("/") and n.lower().endswith((".jpg", ".jpeg", ".png"))]
    if limit: names = names[:limit]
    print(f"[{style}] {len(names)} 幅待处理")

    cur = conn.cursor()
    n_ok = n_dup = n_bad = 0
    t0 = time.time()
    for i, name in enumerate(names, 1):
        try:
            # name = <style>/<artist-slug>/<title-slug>.jpg
            rel = name.split("/", 1)[1] if "/" in name else name   # 去掉首层 <style>/
            seg = rel.split("/")
            if len(seg) >= 2:
                artist_slug = seg[0]; title_slug = os.path.splitext(seg[-1])[0]
            else:
                artist_slug = "unknown"; title_slug = os.path.splitext(seg[-1])[0]

            raw = iz.read(name)
            sha = hashlib.sha256(raw).hexdigest()

            cur.execute("SELECT 1 FROM files WHERE sha256=%s LIMIT 1", (sha,))
            if cur.fetchone():
                n_dup += 1; continue

            try:
                im = Image.open(io.BytesIO(raw)); im.load()
                w, h = im.size
                ph = str(imagehash.phash(im.convert("RGB")))
            except Exception as e:
                n_bad += 1; print(f"  ✗坏图 {name}: {repr(e)[:50]}"); continue
            if min(w, h) < MIN_SIDE:
                n_bad += 1; continue

            ext = os.path.splitext(seg[-1])[1].lower().lstrip(".") or "jpg"
            cos_key = f"{DEST_PREFIX}{style}/{artist_slug}/{title_slug}.{ext}"

            if dry:
                n_ok += 1
            else:
                CL.put_object(Bucket=SRC_BUCKET, Key=cos_key, Body=raw,
                              ContentType=f"image/{'jpeg' if ext in ('jpg','jpeg') else ext}")
                artist_id = "wikiart:" + artist_slug
                cur.execute(
                    "INSERT INTO artists(artist_id,name_en,created_at) VALUES(%s,%s,now()) "
                    "ON CONFLICT (artist_id) DO NOTHING",
                    (artist_id, deslug_name(artist_slug)))
                cur.execute(
                    "INSERT INTO works(title,artist_id,school,source_batch,src_work_id) "
                    "VALUES(%s,%s,%s,%s,%s) RETURNING work_id",
                    (deslug_title(title_slug), artist_id, style, batch_id, name))
                work_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO files(work_id,cos_key,sha256,phash,width,height,bytes,fmt,source_batch,src_file_id,created_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (cos_key) DO NOTHING "
                    "RETURNING file_id",
                    (work_id, cos_key, sha, ph, w, h, len(raw), ext, batch_id, name))
                fid = cur.fetchone()
                if fid:
                    cur.execute("UPDATE works SET primary_file_id=%s WHERE work_id=%s", (fid[0], work_id))
                conn.commit()
                n_ok += 1
        except Exception as e:
            conn.rollback()
            n_bad += 1; print(f"  ✗错误 {name}: {repr(e)[:80]}")

        if i % 100 == 0:
            sp = time.time() - t0
            print(f"  {i}/{len(names)}  ok={n_ok} dup={n_dup} bad={n_bad}  {i/sp:.1f}幅/s")
    print(f"[{style}] 完成 ok={n_ok} dup={n_dup} bad={n_bad}  用时{time.time()-t0:.0f}s")
    return n_ok, n_dup, n_bad

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style"); ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--limit", type=int); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.list:
        for s in list_styles(): print(" ", style_name(s))
        return

    styles = list_styles()
    if a.style:
        styles = [s for s in styles if style_name(s) == a.style]
        if not styles: sys.exit(f"找不到画派 {a.style}")
    elif not a.all:
        sys.exit("需指定 --style <name> 或 --all 或 --list")

    conn = pg_conn(); cur = conn.cursor()
    batch_id = f"wikiart:{a.style or 'all'}:{int(os.path.getmtime(__file__))}"
    if not a.dry_run:
        cur.execute("INSERT INTO ingest_batches(batch_id,source_name,note) VALUES(%s,%s,%s) "
                    "ON CONFLICT (batch_id) DO NOTHING",
                    (batch_id, "wikiart", f"WikiArt.zip {'all' if a.all else a.style}"))
        conn.commit()

    tot = [0,0,0]
    for s in styles:
        r = ingest_style(s, batch_id, conn, limit=a.limit, dry=a.dry_run)
        for j in range(3): tot[j] += r[j]
    if not a.dry_run:
        cur.execute("UPDATE ingest_batches SET n_files=%s, n_works=%s WHERE batch_id=%s",
                    (tot[0], tot[0], batch_id))
        conn.commit()
    print(f"\n>>> 全部完成 ok={tot[0]} dup={tot[1]} bad={tot[2]}  batch={batch_id}")
    conn.close()

if __name__ == "__main__":
    main()
