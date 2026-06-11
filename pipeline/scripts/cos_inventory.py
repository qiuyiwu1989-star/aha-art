#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描 aha 项目在 COS 的全部数据,生成 dashboard 用的 cos_inventory.json。
数据存储层(治理上游)的总览:各数据区文件数/体积 + COS→已灌库 进度对照。
用法: python3 cos_inventory.py  → 写 web/data/cos_inventory.json(+部署目录)
"""
import os, re, json, datetime
from qcloud_cos import CosConfig, CosS3Client
import psycopg2

OUT = ["/home/ubuntu/users/qiuyiwu/aha-art/web/data/cos_inventory.json",
       "/data/pub/p/aha/data/cos_inventory.json"]
BK = "aha-1254041526"

def cos():
    d = json.load(open(os.path.expanduser("~/.aha_cos.json")))
    return CosS3Client(CosConfig(Region=d["region"], SecretId=d["secret_id"], SecretKey=d["secret_key"]))
def pg():
    d = json.load(open(os.path.expanduser("~/.aha_pg.json")))
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

C = cos()
def scan(bucket, prefix, want_ori=False):
    """返回 (文件数, 字节, 垃圾数, workImage_ori大图数)。稳健末键分页。"""
    n = junk = ori = 0; sz = 0; marker = ""; last = None
    while True:
        r = C.list_objects(Bucket=bucket, Prefix=prefix, Marker=marker, MaxKeys=1000)
        for o in r.get("Contents", []):
            k = o["Key"]; b = k.rsplit("/", 1)[-1]
            if k.endswith("/"): continue
            n += 1; sz += int(o["Size"])
            if b.startswith("._") or b == ".DS_Store": junk += 1; continue
            if want_ori and "workImage_ori/" in k and re.search(r'\.(jpg|jpeg|png|tif)$', b, re.I): ori += 1
            last = k
        if r.get("IsTruncated") == "true": marker = r.get("NextMarker") or last
        else: break
    return n, sz, junk, ori

# 已灌库计数(按来源)
con = pg(); cur = con.cursor()
def ingested(like):
    cur.execute("select count(*) from works where source_batch like %s", (like,)); return cur.fetchone()[0]

areas = []
# 1) 油画数据集(主力,在传)
n, sz, junk, ori = scan(BK, "artworks/油画数据集/", want_ori=True)
areas.append({"key": "yh", "name": "世界大师油画全集", "files": n, "bytes": sz, "junk": junk,
              "ingestable": ori, "ingested": ingested("yh%"),
              "quality": "高清 14.8MP", "note": "元数据四表齐全·正在上传", "tag": "主力"})
# 2) yishujia
n, sz, junk, _ = scan(BK, "artworks/yishujia/")
areas.append({"key": "yishujia", "name": "yishujia 高清裸图", "files": n, "bytes": sz, "junk": junk,
              "ingestable": n, "ingested": ingested("yishujia%"),
              "quality": "高清 10MP", "note": "零元数据·已VLM描述", "tag": "高清无标"})
# 3) nbfox
n, sz, junk, _ = scan(BK, "artworks/nbfox/images/")
areas.append({"key": "nbfox", "name": "nbfox 麦田名画", "files": n, "bytes": sz, "junk": junk,
              "ingestable": n, "ingested": ingested("nbfox%"),
              "quality": "缩略图 0.4MP", "note": "含占位图·需清洗", "tag": "低清"})
# 4) wikiart(zip 存档)
n, sz, junk, _ = scan(BK, "wikiart/")
areas.append({"key": "wikiart", "name": "WikiArt 数据集", "files": n, "bytes": sz, "junk": junk,
              "ingestable": None, "ingested": ingested("wikiart%"),
              "quality": "缩略图 0.3MP", "note": "原始存档(WikiArt1+3+meta_gen)·图已解压灌库·与下方解压图重复", "tag": "存档备份"})
# 5) wikiart 解压后的单图
n2, sz2, _, _ = scan(BK, "artworks/wikiart/")
areas.append({"key": "wikiart_img", "name": "WikiArt 解压单图", "files": n2, "bytes": sz2, "junk": 0,
              "ingestable": n2, "ingested": ingested("wikiart%"),
              "quality": "缩略图 0.3MP", "note": "15流派·灌库后的规范图", "tag": "已入库"})

total_files = sum(a["files"] for a in areas)
total_bytes = sum(a["bytes"] for a in areas)
con.close()

out = {
    "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    "bucket": BK + " (ap-shanghai)",
    "summary": {"areas": len(areas), "files": total_files, "bytes": total_bytes},
    "areas": areas,
    "related": [
        {"name": "油画元数据库 (4张SQL表)", "where": "opendesign-1254041526/datasets/油画数据库.zip", "note": "26MB·还原作者/年代/题材的钥匙"},
        {"name": "yishujia 原桶", "where": "yishujia-1254041526", "note": "34,324文件/72.7GB·勿动·只读"},
    ],
}
for p in OUT:
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(out, open(p, "w"), ensure_ascii=False, indent=1)
        print("写", p)
    except Exception as e:
        print("跳过", p, e)
print(f"汇总: {len(areas)} 区 / {total_files:,} 文件 / {total_bytes/1e9:.1f} GB")
