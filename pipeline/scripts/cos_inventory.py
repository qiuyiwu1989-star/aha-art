#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描 aha 项目在 COS 的全桶数据,生成 cos_inventory.json + cos_report.html。
覆盖所有顶层目录,含文件格式分布、目录结构、灌库进度。
用法: python3 cos_inventory.py
"""
import os, re, json, datetime
from collections import defaultdict
from qcloud_cos import CosConfig, CosS3Client
import psycopg2

BK = "aha-1254041526"
OUT_JSON = ["/home/ubuntu/users/qiuyiwu/aha-art/web/data/cos_inventory.json",
            "/data/pub/p/aha/data/cos_inventory.json",
            "/data/pub/p/dam/cos/inventory.json"]
OUT_HTML = ["/home/ubuntu/users/qiuyiwu/aha-art/web/cos_report.html",
            "/data/pub/p/aha/cos_report.html",
            "/data/pub/p/dam/cos/index.html"]

def cos():
    d = json.load(open(os.path.expanduser("~/.aha_cos.json")))
    return CosS3Client(CosConfig(Region=d["region"], SecretId=d["secret_id"], SecretKey=d["secret_key"]))

def pg():
    d = json.load(open(os.path.expanduser("~/.aha_pg.json")))
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

C = cos()

# ── 扫描函数 ──────────────────────────────────────────────
def scan_prefix(bucket, prefix, detail=False):
    """扫描指定前缀,返回 {files, bytes, junk, exts, subdirs}。"""
    n = junk = 0; sz = 0; marker = ""; last = None
    exts = defaultdict(lambda: {"files": 0, "bytes": 0})
    subdirs = defaultdict(lambda: {"files": 0, "bytes": 0})
    while True:
        r = C.list_objects(Bucket=bucket, Prefix=prefix, Marker=marker, MaxKeys=1000)
        for o in r.get("Contents", []):
            k = o["Key"]; b = k.rsplit("/", 1)[-1]
            if k.endswith("/"): continue
            n += 1; sz += int(o["Size"])
            if b.startswith("._") or b == ".DS_Store": junk += 1
            ext = os.path.splitext(b)[1].lower() or "(无后缀)"
            exts[ext]["files"] += 1; exts[ext]["bytes"] += int(o["Size"])
            if detail:
                rel = k[len(prefix):]
                parts = rel.split("/")
                sub = parts[0] if len(parts) > 1 else "(根)"
                subdirs[sub]["files"] += 1; subdirs[sub]["bytes"] += int(o["Size"])
            last = k
        if r.get("IsTruncated") == "true": marker = r.get("NextMarker") or last
        else: break
    return {"files": n, "bytes": sz, "junk": junk,
            "exts": dict(exts), "subdirs": dict(subdirs) if detail else {}}

def scan_whole_bucket(bucket):
    """扫描整个 bucket,按顶层目录分组。"""
    stats = defaultdict(lambda: {"files": 0, "bytes": 0})
    marker = ""
    while True:
        r = C.list_objects(Bucket=bucket, Marker=marker, MaxKeys=1000)
        for o in r.get("Contents", []):
            k = o["Key"]
            if k.endswith("/"): continue
            sz = int(o["Size"])
            top = k.split("/")[0] if "/" in k else "(根)"
            stats[top]["files"] += 1; stats[top]["bytes"] += sz
        if r.get("IsTruncated") == "true":
            marker = r.get("NextMarker") or o["Key"]
        else:
            break
    return dict(stats)

# ── 灌库计数 ──────────────────────────────────────────────
try:
    con = pg(); cur = con.cursor()
    def ingested(like):
        cur.execute("select count(*) from works where source_batch like %s", (like,))
        return cur.fetchone()[0]
    HAS_PG = True
except Exception as e:
    print(f"PG 不可用({e}),跳过灌库统计")
    HAS_PG = False
    def ingested(like): return None

# ── 定义扫描区域 ──────────────────────────────────────────
AREA_DEFS = [
    {"key": "yh", "prefix": "artworks/油画数据集/", "name": "世界大师油画全集",
     "quality": "高清 14.8MP", "tag": "主力", "ingest_like": "yh%", "detail": True},
    {"key": "_generated", "prefix": "artworks/_generated/", "name": "AI 生成产物",
     "quality": "混合", "tag": "生成", "detail": True},
    {"key": "yishujia", "prefix": "artworks/yishujia/", "name": "yishujia 高清裸图",
     "quality": "高清 10MP", "tag": "高清无标", "ingest_like": "yishujia%"},
    {"key": "guohua", "prefix": "artworks/国画浏览版/", "name": "国画浏览版",
     "quality": "高清", "tag": "国画", "detail": True},
    {"key": "wikiart_img", "prefix": "artworks/wikiart/", "name": "WikiArt 解压单图",
     "quality": "缩略图 0.3MP", "tag": "已入库", "ingest_like": "wikiart%"},
    {"key": "nbfox", "prefix": "artworks/nbfox/", "name": "nbfox 麦田名画",
     "quality": "缩略图 0.4MP", "tag": "低清", "ingest_like": "nbfox%"},
    {"key": "_thumb", "prefix": "artworks/_thumb/", "name": "缩略图缓存",
     "quality": "缩略图", "tag": "缓存"},
    {"key": "zaowuyun", "prefix": "zaowuyun/", "name": "造物云",
     "quality": "混合", "tag": "造物云", "detail": True},
    {"key": "wikiart_zip", "prefix": "wikiart/", "name": "WikiArt 存档",
     "quality": "zip", "tag": "存档备份", "ingest_like": "wikiart%"},
    {"key": "newyear", "prefix": "NewYearPaintings/", "name": "年画",
     "quality": "高清", "tag": "年画", "detail": True},
    {"key": "artists", "prefix": "artists/", "name": "画家资料",
     "quality": "资料", "tag": "元数据"},
    {"key": "jiangnan", "prefix": "jiangnan/", "name": "江南素材",
     "quality": "素材", "tag": "素材"},
]

print("开始扫描 COS 全桶...")
areas = []
for ad in AREA_DEFS:
    print(f"  扫描 {ad['name']}...", end=" ", flush=True)
    r = scan_prefix(BK, ad["prefix"], detail=ad.get("detail", False))
    ing = ingested(ad["ingest_like"]) if HAS_PG and "ingest_like" in ad else None
    area = {
        "key": ad["key"], "name": ad["name"],
        "files": r["files"], "bytes": r["bytes"], "junk": r["junk"],
        "quality": ad["quality"], "tag": ad["tag"],
        "exts": r["exts"], "subdirs": r["subdirs"],
        "ingested": ing,
    }
    areas.append(area)
    print(f"{r['files']:,} 文件 / {r['bytes']/1e9:.1f} GB")

total_files = sum(a["files"] for a in areas)
total_bytes = sum(a["bytes"] for a in areas)

# 整桶校验
print("\n整桶全量扫描校验...")
bucket_stats = scan_whole_bucket(BK)
bucket_total_files = sum(v["files"] for v in bucket_stats.values())
bucket_total_bytes = sum(v["bytes"] for v in bucket_stats.values())

if HAS_PG: con.close()

# ── 输出 JSON ─────────────────────────────────────────────
now = datetime.datetime.now()
out = {
    "updated": now.strftime("%Y-%m-%d %H:%M"),
    "bucket": BK + " (ap-shanghai)",
    "summary": {"areas": len(areas), "files": total_files, "bytes": total_bytes,
                "bucket_files": bucket_total_files, "bucket_bytes": bucket_total_bytes},
    "areas": areas,
    "bucket_top": bucket_stats,
    "related": [
        {"name": "油画元数据库 (4张SQL表)", "where": "opendesign-1254041526/datasets/油画数据库.zip", "note": "26MB"},
        {"name": "yishujia 原桶", "where": "yishujia-1254041526", "note": "只读"},
    ],
}
for p in OUT_JSON:
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(out, open(p, "w"), ensure_ascii=False, indent=1)
        print("写", p)
    except Exception as e:
        print("跳过", p, e)

# ── 输出 HTML ─────────────────────────────────────────────
def fmt_bytes(b):
    if b >= 1e12: return f"{b/1e12:.2f} TB"
    if b >= 1e9: return f"{b/1e9:.1f} GB"
    if b >= 1e6: return f"{b/1e6:.1f} MB"
    return f"{b/1e3:.0f} KB"

def ext_rows(exts):
    if not exts: return ""
    items = sorted(exts.items(), key=lambda x: -x[1]["files"])
    rows = ""
    for ext, v in items[:10]:
        rows += f"<tr><td>{ext}</td><td>{v['files']:,}</td><td>{fmt_bytes(v['bytes'])}</td></tr>\n"
    return rows

def subdir_rows(subdirs):
    if not subdirs: return ""
    items = sorted(subdirs.items(), key=lambda x: -x[1]["files"])
    rows = ""
    for sub, v in items[:15]:
        rows += f"<tr><td>{sub}</td><td>{v['files']:,}</td><td>{fmt_bytes(v['bytes'])}</td></tr>\n"
    return rows

def area_card(a):
    ing_str = ""
    if a["ingested"] is not None:
        pct = a["ingested"] / a["files"] * 100 if a["files"] else 0
        bar_color = "#4ade80" if pct >= 90 else "#facc15" if pct >= 50 else "#f87171"
        ing_str = f'''
        <div class="ingest">
          <span>灌库 {a["ingested"]:,} / {a["files"]:,} ({pct:.0f}%)</span>
          <div class="bar"><div class="bar-fill" style="width:{min(pct,100):.0f}%;background:{bar_color}"></div></div>
        </div>'''

    ext_table = ""
    if a["exts"]:
        ext_table = f'''
        <details><summary>文件格式分布</summary>
        <table class="inner"><tr><th>格式</th><th>文件数</th><th>容量</th></tr>
        {ext_rows(a["exts"])}</table></details>'''

    sub_table = ""
    if a["subdirs"]:
        sub_table = f'''
        <details open><summary>目录结构</summary>
        <table class="inner"><tr><th>目录</th><th>文件数</th><th>容量</th></tr>
        {subdir_rows(a["subdirs"])}</table></details>'''

    return f'''
    <div class="card">
      <div class="card-head">
        <span class="tag">{a["tag"]}</span>
        <h3>{a["name"]}</h3>
        <span class="stat">{a["files"]:,} 文件 / {fmt_bytes(a["bytes"])}</span>
      </div>
      <div class="meta">质量: {a["quality"]}  |  垃圾文件: {a["junk"]}</div>
      {ing_str}
      {ext_table}
      {sub_table}
    </div>'''

cards_html = "\n".join(area_card(a) for a in areas)

# bucket 顶层表格
bucket_rows = ""
for top, v in sorted(bucket_stats.items(), key=lambda x: -x[1]["bytes"]):
    bucket_rows += f"<tr><td>{top}</td><td>{v['files']:,}</td><td>{fmt_bytes(v['bytes'])}</td></tr>\n"

html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DAM / COS 存储报告</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:#0f0f0f;color:#e0e0e0;padding:24px;max-width:1200px;margin:0 auto}}
h1{{font-size:20px;font-weight:600;margin-bottom:4px}}
.updated{{color:#888;font-size:13px;margin-bottom:24px}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:32px}}
.s-card{{background:#1a1a1a;border-radius:8px;padding:16px;text-align:center}}
.s-card .num{{font-size:28px;font-weight:700;color:#fff}}
.s-card .label{{font-size:12px;color:#888;margin-top:4px}}
.card{{background:#1a1a1a;border-radius:10px;padding:20px;margin-bottom:16px}}
.card-head{{display:flex;align-items:center;gap:12px;margin-bottom:8px;flex-wrap:wrap}}
.card-head h3{{font-size:16px;font-weight:600}}
.tag{{background:#2a2a2a;color:#aaa;font-size:11px;padding:2px 8px;border-radius:4px}}
.stat{{color:#aaa;font-size:13px;margin-left:auto}}
.meta{{color:#666;font-size:12px;margin-bottom:8px}}
.ingest{{margin:8px 0}}
.ingest span{{font-size:12px;color:#aaa}}
.bar{{height:6px;background:#2a2a2a;border-radius:3px;margin-top:4px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:3px;transition:width .3s}}
details{{margin-top:10px}}
summary{{font-size:13px;color:#888;cursor:pointer;user-select:none}}
summary:hover{{color:#ccc}}
table.inner{{width:100%;border-collapse:collapse;margin-top:6px;font-size:12px}}
table.inner th{{text-align:left;color:#666;font-weight:500;padding:4px 8px;border-bottom:1px solid #2a2a2a}}
table.inner td{{padding:4px 8px;border-bottom:1px solid #1f1f1f}}
table.inner tr:hover td{{background:#1f1f1f}}
.section-title{{font-size:14px;font-weight:600;color:#888;margin:24px 0 12px;text-transform:uppercase;letter-spacing:1px}}
</style>
</head>
<body>
<nav style="display:flex;align-items:center;gap:16px;margin-bottom:20px">
  <a href="/" style="color:#888;text-decoration:none;font-size:13px">← DAM</a>
  <h1>COS 存储报告</h1>
</nav>
<div class="updated">存储桶 {BK} (ap-shanghai) &middot; 扫描于 {now.strftime("%Y-%m-%d %H:%M")}</div>

<div class="summary">
  <div class="s-card"><div class="num">{total_files:,}</div><div class="label">总文件数</div></div>
  <div class="s-card"><div class="num">{fmt_bytes(total_bytes)}</div><div class="label">总容量</div></div>
  <div class="s-card"><div class="num">{len(areas)}</div><div class="label">数据分区</div></div>
  <div class="s-card"><div class="num">{bucket_total_files:,}</div><div class="label">桶内全量文件</div></div>
</div>

<div class="section-title">数据分区</div>
{cards_html}

<div class="section-title">桶顶层目录</div>
<div class="card">
<table class="inner">
<tr><th>目录</th><th>文件数</th><th>容量</th></tr>
{bucket_rows}
</table>
</div>

</body>
</html>'''

for p in OUT_HTML:
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(html)
        print("写", p)
    except Exception as e:
        print("跳过", p, e)

print(f"\n汇总: {len(areas)} 区 / {total_files:,} 文件 / {fmt_bytes(total_bytes)}")
print(f"桶全量: {bucket_total_files:,} 文件 / {fmt_bytes(bucket_total_bytes)}")
