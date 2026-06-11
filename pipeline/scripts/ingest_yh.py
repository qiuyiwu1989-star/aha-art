#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""油画数据集(世界大师油画全集)来源适配器 → aha works/files。

元数据来自用户的 MySQL dump(opendesign 桶 datasets/油画数据库.zip 解出):
  al_artist.sql  艺术家(中文名/西文名/生卒/出生地/国籍/简介/师承)
  al_work.sql    作品(name/en_name/author/work_period/material/size/imp_period画派/
                 keywords/subject_names/imgl图片路径/artist_ids→al_artist)
图在 COS `artworks/油画数据集/yh/<imgl>`(目前仅传了约 1.2 万张大图,SQL 有 7.2 万条;
本适配器只灌"图已存在"的,幂等,后续补图重跑即增量)。

用法: python3 ingest_yh.py [--sql-dir /tmp/yh_sql/油画数据库] [--limit N] [--workers 12]
"""
import os, sys, io, re, json, hashlib, argparse, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from qcloud_cos import CosConfig, CosS3Client
from PIL import Image
import imagehash
import psycopg2

Image.MAX_IMAGE_PIXELS = None
BUCKET = "aha-1254041526"
IMG_BASE = "artworks/油画数据集/yh/"     # imgl 相对此前缀
BATCH = "yh:油画数据集"

def _cfg(p): return json.load(open(os.path.expanduser(p)))
def cos_client():
    d = _cfg("~/.aha_cos.json")
    # Timeout/Retry 必须设:否则 get_object 在高并发下可能无限挂死(实测会 stall 整个进程)
    return CosS3Client(CosConfig(Region=d["region"], SecretId=d["secret_id"], SecretKey=d["secret_key"],
                                 Timeout=30))
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

# ---------- MySQL dump 单元组解析(处理引号/转义/内嵌逗号括号) ----------
def split_row(t, i):
    """t[i]=='(' ,返回该元组字段列表(到匹配的 ')')。"""
    i += 1; fields = []
    n = len(t)
    while i < n:
        while t[i] in " \n\r\t": i += 1
        if t[i] == "'":
            i += 1; buf = []
            while True:
                ch = t[i]
                if ch == "\\":
                    nx = t[i+1]
                    buf.append({"n": "\n", "t": "\t", "r": "\r", "0": "\0"}.get(nx, nx)); i += 2
                elif ch == "'":
                    if t[i+1] == "'": buf.append("'"); i += 2
                    else: i += 1; break
                else:
                    buf.append(ch); i += 1
            fields.append("".join(buf))
        else:
            j = i
            while t[j] not in ",)": j += 1
            tok = t[i:j].strip(); i = j
            fields.append(None if tok == "NULL" else tok)
        while t[i] in " \n\r\t": i += 1
        if t[i] == ",": i += 1; continue
        if t[i] == ")": break
    return fields

def iter_rows(sql_path, table):
    txt = open(sql_path, encoding="utf-8", errors="ignore").read()
    pat = re.compile(r"INSERT INTO `%s` VALUES " % re.escape(table))
    for m in pat.finditer(txt):
        k = txt.index("(", m.end() - 1)
        yield split_row(txt, k)

def _year(s):
    if not s: return None
    m = re.search(r"(\d{3,4})", str(s))
    return int(m.group(1)) if m else None

def parse_size(s):
    if not s: return (None, None)
    m = re.search(r"(\d+(?:\.\d+)?)\s*[x×X*]\s*(\d+(?:\.\d+)?)", s)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)

# ---------- 加载艺术家字典 ----------
def load_artists(sql_dir):
    # al_artist 列: 0id 1name 2en_name 3by_name 4born_date 5born_address 6dead_date 7dead_address ... 16country
    d = {}
    for r in iter_rows(os.path.join(sql_dir, "al_artist.sql"), "al_artist"):
        if len(r) < 17: continue
        # 注:r[16] country 是数字编码(无码表),不入 nationality;region 用出生地文本
        d[r[0]] = {"name_cn": (r[1] or None), "name_en": (r[2] or None),
                   "born": _year(r[4]), "death": _year(r[6]),
                   "nationality": None, "region": (r[5] or None)}
    return d

def list_existing(prefix):
    keys = set(); marker = ""; cl = cos_client()
    while True:
        rr = cl.list_objects(Bucket=BUCKET, Prefix=prefix, Marker=marker, MaxKeys=1000)
        cs = rr.get("Contents", [])
        for x in cs:
            k = x["Key"]
            if k.lower().endswith((".jpg", ".jpeg", ".png")): keys.add(k)
        if rr.get("IsTruncated") == "true" and cs: marker = cs[-1]["Key"]
        else: break
    return keys

# ---------- 灌单件作品(可含多图) ----------
def ingest_one(rec):
    cn = conn(); cur = cn.cursor()
    try:
        # 先读所有图、算指纹;全是已存在(sha256)则整件跳过
        files = []
        for cos_key in rec["cos_keys"]:
            raw = cos().get_object(Bucket=BUCKET, Key=cos_key)["Body"].get_raw_stream().read()
            sha = hashlib.sha256(raw).hexdigest()
            cur.execute("SELECT 1 FROM files WHERE sha256=%s LIMIT 1", (sha,))
            if cur.fetchone(): continue
            im = Image.open(io.BytesIO(raw)); w, h = im.size      # 宽高只读文件头,不全解码
            im.draft("RGB", (512, 512))                            # 让 JPEG 解码器直接降采样,省内存
            im = im.convert("RGB"); im.thumbnail((512, 512))       # 缩小后再算 phash(对缩放鲁棒)
            ph = str(imagehash.phash(im))
            files.append((cos_key, sha, ph, w, h, len(raw), cos_key.rsplit(".", 1)[-1].lower()))
        if not files: cn.commit(); return "dup"

        a = rec["artist"]
        cur.execute("""INSERT INTO artists(artist_id,name_cn,name_en,nationality,region,born,death,created_at)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (artist_id) DO NOTHING""",
                    (rec["artist_id"], a["name_cn"], a["name_en"], a["nationality"], a["region"], a["born"], a["death"]))
        cur.execute("""INSERT INTO works(title,artist_id,year,school,medium,w_cm,h_cm,source_batch,src_work_id)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING work_id""",
                    (rec["title"], rec["artist_id"], rec["year"], rec["school"], rec["medium"],
                     rec["w_cm"], rec["h_cm"], BATCH, rec["work_id"]))
        work_id = cur.fetchone()[0]
        best = None  # (px, file_id) 选最大图当主图
        for cos_key, sha, ph, w, h, sz, ext in files:
            cur.execute("""INSERT INTO files(work_id,cos_key,sha256,phash,width,height,bytes,fmt,source_batch,src_file_id,created_at)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (cos_key) DO NOTHING RETURNING file_id""",
                        (work_id, cos_key, sha, ph, w, h, sz, ext, BATCH, rec["work_id"]))
            fid = cur.fetchone()
            if fid and (best is None or w*h > best[0]): best = (w*h, fid[0])
        if best:
            cur.execute("UPDATE works SET primary_file_id=%s WHERE work_id=%s", (best[1], work_id))
        cn.commit()
        return "ok"
    except Exception as e:
        cn.rollback()
        return f"bad:{repr(e)[:60]}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql-dir", default=os.path.join(os.path.dirname(__file__), "_yh_sql", "油画数据库"))
    ap.add_argument("--limit", type=int); ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--skip-done", action="store_true", help="下载前剔掉已入库的作品(按 src_work_id),增量补图用")
    a = ap.parse_args()

    print("列 COS 已有大图…")
    have = list_existing(IMG_BASE)
    print(f"  COS 图片 {len(have)}")
    print("加载 al_artist…")
    artists = load_artists(a.sql_dir)
    print(f"  艺术家 {len(artists)}")

    print("解析 al_work(作品元数据)…")
    work_meta = {}
    for r in iter_rows(os.path.join(a.sql_dir, "al_work.sql"), "al_work"):
        if len(r) < 49: continue
        work_meta[r[0]] = r

    print("解析 al_work_files 并按作品聚合(以此表为图—作品真链接)…")
    # al_work_files 列: 0id 1work_id 2imgx 3imgs 4imgl
    work_imgs = {}
    for r in iter_rows(os.path.join(a.sql_dir, "al_work_files.sql"), "al_work_files"):
        if len(r) < 5 or not r[4]: continue
        cos_key = IMG_BASE + r[4].lstrip("/")
        if cos_key not in have: continue
        work_imgs.setdefault(r[1], []).append(cos_key)
    print(f"  有图作品 {len(work_imgs)}  覆盖图片 {sum(len(v) for v in work_imgs.values())}")

    todo = []; n_nometa = 0
    for work_id, keys in work_imgs.items():
        r = work_meta.get(work_id)
        if not r:
            n_nometa += 1
            todo.append({"work_id": work_id, "title": None, "artist_id": "yh:unknown",
                         "artist": {"name_cn": None, "name_en": None, "born": None, "death": None,
                                    "nationality": None, "region": None},
                         "year": None, "school": None, "medium": None, "w_cm": None, "h_cm": None,
                         "cos_keys": sorted(set(keys))})
            continue
        aid_raw = (r[48] or "").split(",")[0].strip()
        if aid_raw and aid_raw in artists:
            art = dict(artists[aid_raw]); artist_id = "yh:" + aid_raw
            if not art["name_cn"]: art["name_cn"] = r[9]
        else:
            artist_id = "yh:name:" + (r[9] or "unknown")
            art = {"name_cn": r[9] or None, "name_en": r[31] or None, "born": None, "death": None,
                   "nationality": None, "region": None}
        w_cm, h_cm = parse_size(r[14])
        todo.append({"work_id": work_id, "title": (r[7] or None), "artist_id": artist_id, "artist": art,
                     "year": _year(r[10]), "school": (r[39] or None), "medium": (r[13] or None),
                     "w_cm": w_cm, "h_cm": h_cm, "cos_keys": sorted(set(keys))})
    if a.skip_done:
        cn = pg_conn(); cur = cn.cursor()
        cur.execute("select src_work_id from works where source_batch=%s and src_work_id is not null", (BATCH,))
        done = {row[0] for row in cur.fetchall()}; cn.close()
        before = len(todo)
        todo = [t for t in todo if t["work_id"] not in done]
        print(f"  跳过已入库 {before - len(todo)} 件,实际待灌 {len(todo)}")
    if a.limit: todo = todo[:a.limit]
    print(f"  待灌作品 {len(todo)}  (无元数据孤儿 {n_nometa})")

    n = {"ok": 0, "dup": 0, "bad": 0}; t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(ingest_one, rec) for rec in todo]
        for i, f in enumerate(as_completed(futs), 1):
            res = f.result(); key = res if res in ("ok", "dup") else "bad"
            n[key] += 1
            if key == "bad" and n["bad"] <= 10: print("  ", res)
            if i % 500 == 0:
                print(f"  {i}/{len(todo)}  ok={n['ok']} dup={n['dup']} bad={n['bad']}  {i/(time.time()-t0):.1f}/s")
    print(f"\n>>> 油画数据集 完成 ok={n['ok']} dup={n['dup']} bad={n['bad']}  用时{time.time()-t0:.0f}s  batch={BATCH}")

if __name__ == "__main__":
    main()
