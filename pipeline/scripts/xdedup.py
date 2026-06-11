#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全局跨源近重复去重(global cross-source dedup)。

per-batch dedup 只在批内、且 wikiart 8万级退化为精确分组;之前 xsource_merge 只记了
dup_clusters 没真降级。本脚本对**全库**(所有来源)做一次近重复聚类:
  phash 64bit,汉明距离 ≤ threshold;numpy 16bit-LUT popcount 向量化(每件 XOR 全量)。
  并查集成簇 → 每簇选 1 主图(优先 status:kept>archived>pending,再高分辨率)→ 其余 status=dup
  (reason='xsrc_dup'),记 dup_clusters。幂等(已 dup 不参与)。

用法: python3 xdedup.py [--threshold 6] [--dry-run]
"""
import os, json, argparse, time
import numpy as np
import psycopg2

def pg():
    d = json.load(open(os.path.expanduser("~/.aha_pg.json")))
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

# 16bit popcount LUT
_LUT = np.array([bin(i).count("1") for i in range(1 << 16)], dtype=np.uint16)
def popcount64(x):  # x: uint64 ndarray
    return (_LUT[(x & 0xFFFF).astype(np.uint64).astype(np.int64)]
          + _LUT[((x >> np.uint64(16)) & 0xFFFF).astype(np.int64)]
          + _LUT[((x >> np.uint64(32)) & 0xFFFF).astype(np.int64)]
          + _LUT[((x >> np.uint64(48)) & 0xFFFF).astype(np.int64)]).astype(np.int32)

STATUS_RANK = {"kept": 3, "archived": 2, "pending": 1, "rejected": 0}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    TH = a.threshold

    cn = pg(); cur = cn.cursor()
    # 参与去重:有 phash+primary、且未被标 dup/rejected 的作品(以 primary file 的 phash 为代表)
    cur.execute("""SELECT w.work_id, f.phash, COALESCE(f.width,0)*COALESCE(f.height,0), w.status,
                          split_part(w.source_batch,':',1), f.file_id
                   FROM works w JOIN files f ON f.file_id=w.primary_file_id
                   WHERE f.phash IS NOT NULL AND w.status NOT IN ('dup','rejected')""")
    rows = cur.fetchall()
    n = len(rows)
    print(f"参与去重 {n} 件 (hamming≤{TH})")
    wid = np.array([r[0] for r in rows], dtype=np.int64)
    try:
        ph = np.array([int(r[1], 16) for r in rows], dtype=np.uint64)
    except Exception as e:
        print("phash 解析失败", e); return
    px = np.array([r[2] for r in rows], dtype=np.int64)
    rank = np.array([STATUS_RANK.get(r[3], 1) for r in rows], dtype=np.int32)
    fid = np.array([r[5] for r in rows], dtype=np.int64)

    # union-find
    parent = list(range(n))
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry: parent[max(rx, ry)] = min(rx, ry)

    t0 = time.time()
    for i in range(n):
        d = popcount64(ph ^ ph[i])
        js = np.where(d <= TH)[0]
        for j in js:
            if j != i: union(i, int(j))
        if i % 5000 == 0 and i:
            print(f"  聚类 {i}/{n}  {i/(time.time()-t0):.0f}/s")

    # 成簇
    clusters = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)
    multi = {r: m for r, m in clusters.items() if len(m) > 1}
    n_dup = sum(len(m) - 1 for m in multi.values())
    print(f"近重复簇 {len(multi)} 个,将标 dup {n_dup} 件,保留主图 {len(multi)} 件")

    # 统计跨源簇
    xsrc = 0
    for m in multi.values():
        srcs = {rows[i][4] for i in m}
        if len(srcs) > 1: xsrc += 1
    print(f"  其中跨来源簇 {xsrc} 个")

    if a.dry_run:
        # 抽样展示几个跨源簇
        shown = 0
        for r, m in multi.items():
            srcs = {rows[i][4] for i in m}
            if len(srcs) > 1 and shown < 5:
                print("  样例簇:", [(rows[i][0], rows[i][4], rows[i][2]) for i in m]); shown += 1
        return

    # 落库:每簇选主图(rank 高→px 大),其余标 dup
    dup_ids = []; cluster_rows = []
    for m in multi.values():
        best = max(m, key=lambda i: (rank[i], px[i]))
        keep_wid = int(wid[best])
        losers = [i for i in m if i != best]
        dup_ids += [int(wid[i]) for i in losers]
        cluster_rows.append((keep_wid, [int(fid[i]) for i in m]))
    # 批量更新
    from psycopg2.extras import execute_values
    for k in range(0, len(dup_ids), 1000):
        chunk = dup_ids[k:k+1000]
        cur.execute("UPDATE works SET status='dup', reject_reason='xsrc_dup' WHERE work_id = ANY(%s) AND status<>'dup'", (chunk,))
    execute_values(cur, "INSERT INTO dup_clusters(work_id, member_file_ids, reason) VALUES %s",
                   [(w, mf, f"xsrc_global≤{TH}") for w, mf in cluster_rows])
    cn.commit()
    print(f"✓ 标 dup {len(dup_ids)} 件,新增 dup_clusters {len(cluster_rows)} 个")
    cur.execute("SELECT status,count(*) FROM works GROUP BY status ORDER BY 2 DESC")
    print("  状态分布:", cur.fetchall())
    cn.close()

if __name__ == "__main__":
    main()
