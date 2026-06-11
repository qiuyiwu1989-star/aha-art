#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨源比对择优:WikiArt ↔ 油画数据集(yh)。策略 A = 取长补短。

同一幅画两边都有时(phash 汉明距离 ≤ 阈值):
  · 图像:选分辨率更高者为 primary(通常 yh 高清胜出);
  · 标签:把 WikiArt 的规整流派(movement)回填到 yh 作品的 school(yh 偏杂/空时);
  · 记一个跨源 dup_cluster(reason='xsrc:phash≤d'),低清成员标记为非主(永不物理删)。

用法:
  python3 xsource_merge.py --dry-run            # 只统计+样例,不写库
  python3 xsource_merge.py --apply              # 写 dup_clusters / 回填 school / 设 primary_file_id
  附加 --threshold 6
"""
import json, argparse, time
import numpy as np
import psycopg2

def pg():
    d = json.load(open("/home/ubuntu/.aha_pg.json"))
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

# ---- 64-bit popcount(16-bit LUT 向量化) ----
_LUT = np.array([bin(i).count("1") for i in range(1 << 16)], dtype=np.uint8)
def popcount64(arr):  # arr: uint64 ndarray
    a = arr.view(np.uint64)
    return (_LUT[a & 0xFFFF] + _LUT[(a >> 16) & 0xFFFF]
            + _LUT[(a >> 32) & 0xFFFF] + _LUT[(a >> 48) & 0xFFFF]).astype(np.int16)

def load(cur, where):
    cur.execute(f"""select f.file_id, f.work_id, f.phash, f.cos_key,
                    coalesce(f.width,0)::bigint*coalesce(f.height,0) px, coalesce(f.bytes,0)
                    from files f where f.phash is not null and ({where})""")
    rows = cur.fetchall()
    ph = np.array([int(r[2], 16) for r in rows], dtype=np.uint64)
    return rows, ph

def movement_of(cos_key):  # artworks/wikiart/<movement>/<artist>/<title>.jpg
    p = cos_key.split("/")
    return p[2] if len(p) > 3 and p[1] == "wikiart" else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=int, default=6)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not (a.apply or a.dry_run): a.dry_run = True

    con = pg(); cur = con.cursor()
    yh, yph = load(cur, "f.source_batch like 'yh%'")
    wk, wph = load(cur, "f.cos_key like 'artworks/wikiart/%'")
    print(f"yh 图 {len(yh):,}  |  wikiart 图 {len(wk):,}  |  阈值 ≤{a.threshold}")
    t0 = time.time()

    # 对每个 yh 图,在 wikiart 里找最近邻(yh 是较小集,作 query 循环)
    matches = []   # (yh_idx, wk_idx, dist)
    for i in range(len(yh)):
        d = popcount64(wph ^ yph[i])
        j = int(d.argmin()); dist = int(d[j])
        if dist <= a.threshold:
            matches.append((i, j, dist))
        if (i+1) % 2000 == 0:
            print(f"  比对 {i+1}/{len(yh)}  命中 {len(matches)}  {(i+1)/(time.time()-t0):.0f}/s")
    print(f"\n跨源同画对 {len(matches):,}  用时 {time.time()-t0:.0f}s")

    # 统计择优方向 + 回填可得性
    yh_wins = wk_wins = label_fill = 0
    samples = []
    for (i, j, dist) in matches:
        yh_px, wk_px = yh[i][4], wk[j][4]
        primary_yh = yh_px >= wk_px
        if primary_yh: yh_wins += 1
        else: wk_wins += 1
        mv = movement_of(wk[j][3])
        if mv: label_fill += 1
        if len(samples) < 8:
            samples.append((dist, yh[i][3].split('/')[-1], yh_px, wk[j][3].split('/')[-1], wk_px, mv))
    print(f"择优(图): yh高清胜 {yh_wins:,} | wikiart胜 {wk_wins:,}")
    print(f"可回填 WikiArt 流派标签的 yh 作品: {label_fill:,}")
    print("样例 [dist | yh文件(px) | wikiart文件(px) | 回填流派]:")
    for s in samples:
        print(f"  d{s[0]}  {s[1]}({s[2]/1e6:.1f}MP)  ~  {s[3]}({s[4]/1e6:.2f}MP)  → {s[5]}")

    if not a.apply:
        print("\n[dry-run] 未写库。确认后加 --apply。"); return

    # ---- 应用:写 dup_clusters + 回填 school + 设 primary_file_id ----
    n_clu = n_lbl = n_prim = 0
    for (i, j, dist) in matches:
        yfid, ywid, _, _, ypx, _ = yh[i]
        wfid, wwid, _, wkey, wpx, _ = wk[j]
        primary_fid = yfid if ypx >= wpx else wfid
        primary_wid = ywid if ypx >= wpx else wwid
        cur.execute("""insert into dup_clusters(work_id, member_file_ids, reason, created_at)
                       values(%s,%s,%s,now())""", (primary_wid, [yfid, wfid], f"xsrc:phash≤{dist}"))
        n_clu += 1
        cur.execute("update works set primary_file_id=%s where work_id=%s and primary_file_id is null",
                    (primary_fid, primary_wid)); n_prim += cur.rowcount
        mv = movement_of(wkey)
        if mv:  # 回填规整流派,仅填 yh 空缺(不覆盖已有中文标签,避免中英混杂)
            cur.execute("""update works set school=%s
                           where work_id=%s and (school is null or school='')""",
                        (mv, ywid)); n_lbl += cur.rowcount
        if n_clu % 1000 == 0: con.commit(); print(f"  写入 {n_clu}…")
    con.commit()
    print(f"\n>>> 完成: 跨源簇 {n_clu:,} | 回填流派 {n_lbl:,} | 设主图 {n_prim:,}")

if __name__ == "__main__":
    main()
