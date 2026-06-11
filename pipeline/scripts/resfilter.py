#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""严格筛选:分辨率预闸 + 质量闸(软删=archived,留底可回溯,绝不物理删)。

动机:WikiArt/nbfox 等源有大量低分辨率图(min-side<500),VLM 看的是"艺术价值"
(名画即便缩略图也给高 merit),但缩略图在带放大的画廊里没法看。所以加一道**客观分辨率闸**:
低于下限的不进核心资产(kept),也不浪费 VLM——pending 的直接低分辨率归档。

两个动作:
  A. 已 kept 但 min-side < floor → 降级 archived(reason=low_res),清出核心资产。
  B. pending 且 min-side < floor → 直接 archived(reason=low_res),不送 VLM(省预算)。
质量闸(可选 --quality):已 kept 但 VLM composite < q-floor 或 merit < merit-floor → archived(low_quality_strict)。

用法:
  python3 resfilter.py --sources wikiart --floor 500            # dry-run(默认只统计不改)
  python3 resfilter.py --sources wikiart,nbfox --floor 500 --apply
  python3 resfilter.py --sources all --floor 500 --quality 0.55 --apply
  python3 resfilter.py --restore --reason low_res --sources wikiart --apply   # 反悔:把归档的恢复回 pending
"""
import os, json, sys, argparse
import psycopg2

_PG = json.load(open(os.path.expanduser("~/.aha_pg.json")))


def conn():
    return psycopg2.connect(host=_PG["host"], port=_PG["port"], dbname=_PG["dbname"],
                            user=_PG["user"], password=_PG["password"])


SRC_LIKE = {"wikiart": "wikiart:%", "nbfox": "nbfox:%", "yh": "yh:%", "yishujia": "yishujia:%"}


def src_clause(sources):
    if sources == ["all"]:
        return "TRUE", []
    likes = [SRC_LIKE[s] for s in sources if s in SRC_LIKE]
    if not likes:
        return "TRUE", []
    return "(" + " OR ".join(["w.artist_id LIKE %s"] * len(likes)) + ")", likes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="wikiart", help="逗号分隔:wikiart,nbfox,yh,yishujia 或 all")
    ap.add_argument("--floor", type=int, default=500, help="min-side 分辨率下限(像素)")
    ap.add_argument("--quality", type=float, default=None, help="可选:kept 的 composite 质量下限")
    ap.add_argument("--merit", type=float, default=None, help="可选:kept 的 VLM merit 下限")
    ap.add_argument("--apply", action="store_true", help="真正执行(默认 dry-run)")
    ap.add_argument("--restore", action="store_true", help="反悔:把指定 reason 的 archived 恢复成 pending")
    ap.add_argument("--reason", default="low_res", help="restore 时要恢复的 reject_reason")
    a = ap.parse_args()
    sources = [s.strip() for s in a.sources.split(",") if s.strip()]
    sc, sargs = src_clause(sources)
    c = conn(); cur = c.cursor()

    if a.restore:
        sql = f"""UPDATE works w SET status='pending', reject_reason=NULL, reviewed_at=NULL
                  WHERE status='archived' AND reject_reason=%s AND {sc}"""
        cur.execute(f"SELECT count(*) FROM works w WHERE status='archived' AND reject_reason=%s AND {sc}", [a.reason] + sargs)
        n = cur.fetchone()[0]
        print(f"[restore] reason={a.reason} sources={sources}: {n} 件将恢复为 pending")
        if a.apply:
            cur.execute(sql, [a.reason] + sargs); c.commit(); print(f"  已恢复 {cur.rowcount}")
        else:
            print("  (dry-run,加 --apply 执行)")
        c.close(); return

    # A. 已 kept 低分辨率 → archived(low_res)
    qA = f"""SELECT count(*) FROM works w JOIN files f ON f.file_id=w.primary_file_id
             WHERE w.status='kept' AND {sc} AND least(f.width,f.height) < %s"""
    cur.execute(qA, sargs + [a.floor]); nA = cur.fetchone()[0]
    # B. pending 低分辨率 → archived(low_res),不送 VLM
    qB = f"""SELECT count(*) FROM works w JOIN files f ON f.file_id=w.primary_file_id
             WHERE w.status='pending' AND {sc} AND least(f.width,f.height) < %s"""
    cur.execute(qB, sargs + [a.floor]); nB = cur.fetchone()[0]
    print(f"=== 严格筛选 dry-run｜sources={sources}｜floor={a.floor}px ===")
    print(f"A. 已 kept 但 <{a.floor}px → 降级 archived(low_res):  {nA} 件")
    print(f"B. pending 但 <{a.floor}px → 归档(low_res,跳过VLM):  {nB} 件")

    nQ = 0
    if a.quality is not None or a.merit is not None:
        conds = []
        if a.quality is not None:
            conds.append(f"w.quality < {a.quality}")
        if a.merit is not None:
            conds.append(f"(w.vlm->'quality'->>'merit')::float < {a.merit}")
        qcond = " OR ".join(conds)
        qQ = f"""SELECT count(*) FROM works w JOIN files f ON f.file_id=w.primary_file_id
                 WHERE w.status='kept' AND {sc} AND least(f.width,f.height) >= %s AND ({qcond})"""
        cur.execute(qQ, sargs + [a.floor]); nQ = cur.fetchone()[0]
        print(f"C. 已 kept 且 ≥{a.floor}px 但质量不达标 → archived(low_quality_strict):  {nQ} 件")

    # 剩余 kept
    cur.execute(f"""SELECT count(*) FROM works w JOIN files f ON f.file_id=w.primary_file_id
                    WHERE w.status='kept' AND {sc} AND least(f.width,f.height) >= %s""", sargs + [a.floor])
    keep_after = cur.fetchone()[0] - nQ
    print(f"→ 该源核心资产 kept 将从 {keep_after + nA + nQ} 降到 {keep_after} 件")

    if not a.apply:
        print("\n(dry-run。确认后加 --apply 执行;可 --restore 反悔。)")
        c.close(); return

    # 执行
    cur.execute(f"""UPDATE works w SET status='archived', reject_reason='low_res', is_artwork=true, reviewed_at=now()
                    FROM files f WHERE f.file_id=w.primary_file_id
                    AND w.status='kept' AND {sc} AND least(f.width,f.height) < %s""", sargs + [a.floor])
    aA = cur.rowcount
    cur.execute(f"""UPDATE works w SET status='archived', reject_reason='low_res', reviewed_at=now()
                    FROM files f WHERE f.file_id=w.primary_file_id
                    AND w.status='pending' AND {sc} AND least(f.width,f.height) < %s""", sargs + [a.floor])
    aB = cur.rowcount
    aQ = 0
    if a.quality is not None or a.merit is not None:
        cur.execute(f"""UPDATE works w SET status='archived', reject_reason='low_quality_strict', reviewed_at=now()
                        FROM files f WHERE f.file_id=w.primary_file_id
                        AND w.status='kept' AND {sc} AND least(f.width,f.height) >= %s AND ({qcond})""", sargs + [a.floor])
        aQ = cur.rowcount
    c.commit()
    print(f"\n[applied] kept→archived(low_res): {aA}｜pending→archived(low_res): {aB}｜kept→archived(low_quality): {aQ}")
    c.close()


if __name__ == "__main__":
    main()
