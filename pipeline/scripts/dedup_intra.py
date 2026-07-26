#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""库内近重复去重(CLIP向量聚类):对每个 lib 内部,把余弦≥SIM 的图聚成簇(并查集),
每簇只保留分辨率最高的一张,其余标 status='dup'(隐藏,可逆)。同一画跨来源自动留高清。
用法: python3 dedup_intra.py <lib1,lib2,...> [sim=0.98]"""
import os, json, sys, numpy as np, psycopg2
from collections import defaultdict

LIBS = sys.argv[1].split(',') if len(sys.argv) > 1 else ['artwork']
TH = float(sys.argv[2]) if len(sys.argv) > 2 else 0.98
d = json.load(open(os.path.expanduser('~/.aha_pg.json')))
cn = psycopg2.connect(host=d['host'], port=d['port'], dbname=d['dbname'], user=d['user'], password=d['password'])
cur = cn.cursor()

def find(p, x):
    while p[x] != x:
        p[x] = p[p[x]]; x = p[x]
    return x
def union(p, a, b):
    ra, rb = find(p, a), find(p, b)
    if ra != rb: p[ra] = rb

for lib in LIBS:
    cur.execute("""SELECT a.asset_id, COALESCE(a.width,0)*COALESCE(a.height,0) res, e.embedding::text
                   FROM dam_asset a JOIN dam_embedding e USING(asset_id)
                   WHERE a.lib=%s AND a.status='active'""", (lib,))
    rows = cur.fetchall()
    N = len(rows)
    print(f"[{lib}] 载入 {N} 张 (阈值 {TH})", flush=True)
    if N < 2: continue
    ids = np.array([r[0] for r in rows], dtype=np.int64)
    res = np.array([r[1] for r in rows], dtype=np.int64)
    V = np.vstack([np.fromstring(r[2].strip()[1:-1], sep=',', dtype=np.float32) for r in rows])
    V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-8)
    parent = list(range(N))
    B = 2000
    for s in range(0, N, B):
        sims = V[s:s+B] @ V.T                       # (b, N)
        for i in range(sims.shape[0]):
            gi = s + i
            for j in np.where(sims[i] >= TH)[0]:
                if int(j) > gi: union(parent, gi, int(j))
        print(f"  [{lib}] {min(s+B,N)}/{N}", flush=True)
    clusters = defaultdict(list)
    for i in range(N): clusters[find(parent, i)].append(i)
    dup = []
    nclu = 0
    for members in clusters.values():
        if len(members) < 2: continue
        nclu += 1
        members.sort(key=lambda i: (-res[i], ids[i]))   # 保留分辨率最高(并列取asset_id小)
        dup.extend(int(ids[i]) for i in members[1:])
    print(f"[{lib}] 重复簇 {nclu} 个,隐藏 {len(dup)} 张,保留 {N-len(dup)} 张", flush=True)
    for s in range(0, len(dup), 5000):
        cur.execute("UPDATE dam_asset SET status='dup' WHERE asset_id = ANY(%s)", (dup[s:s+5000],))
    cn.commit()
print("DONE", flush=True)
cur.close(); cn.close()
