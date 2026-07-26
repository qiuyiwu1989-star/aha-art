#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Artist1.0 生成库跨来源去重(A方案):
艺术家平台(ysj-bucket)里凡和 InfMonkeys(带gen元数据)有 ≥SIM 孪生的,标 status='dup'(隐藏,可逆),
保留 InfMonkeys 那份。InfMonkeys 源向量少(~7千),直接 numpy 矩阵比对,最快最准。"""
import os, json, sys, numpy as np, psycopg2
SIM = float(sys.argv[1]) if len(sys.argv) > 1 else 0.99

d = json.load(open(os.path.expanduser('~/.aha_pg.json')))
cn = psycopg2.connect(host=d['host'], port=d['port'], dbname=d['dbname'], user=d['user'], password=d['password'])
cur = cn.cursor()

def load(src):
    cur.execute("""SELECT a.asset_id, e.embedding::text FROM dam_asset a JOIN dam_embedding e USING(asset_id)
                   WHERE a.lib='infmonkeys' AND a.source=%s AND a.status='active'""", (src,))
    rows = cur.fetchall()
    ids = np.array([r[0] for r in rows], dtype=np.int64)
    V = np.vstack([np.fromstring(r[1].strip()[1:-1], sep=',', dtype=np.float32) for r in rows]) if rows else np.zeros((0,512),np.float32)
    V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-8)
    return ids, V

print("加载 InfMonkeys 源向量…", flush=True)
iid, I = load('infmonkeys')
print(f"  InfMonkeys {len(iid)} 个", flush=True)
print("加载 艺术家平台(ysj-bucket) 源向量…", flush=True)
yid, Y = load('ysj-bucket')
print(f"  艺术家平台 {len(yid)} 个", flush=True)

dup = []
B = 4000
for s in range(0, len(yid), B):
    sims = Y[s:s+B] @ I.T          # (b, Ni) 余弦相似度
    mx = sims.max(axis=1)
    for k, m in enumerate(mx):
        if m >= SIM:
            dup.append(int(yid[s+k]))
    print(f"  比对 {min(s+B,len(yid))}/{len(yid)}, 累计 dup {len(dup)}", flush=True)

print(f"阈值 {SIM}:标记重复 {len(dup)} / {len(yid)} 张", flush=True)
for s in range(0, len(dup), 5000):
    cur.execute("UPDATE dam_asset SET status='dup' WHERE asset_id = ANY(%s)", (dup[s:s+5000],))
cn.commit()
print("已标 status='dup'(可逆:UPDATE 回 active)", flush=True)
cur.close(); cn.close()
