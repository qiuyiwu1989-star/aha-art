#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 aha-art-demo 的 226 幅手工精选(gallery_works.json)灌进核心库。

为什么:首页 museum.html 改吃 /cat/exhibit(DB)后,这批最早的精选要保留进馆。
做法:每幅 → artists(demo:slug) + works(kept/exhibited) + files(本地图 cos_key=img/...);
     vlm 按 catalog_api /exhibit 期望的形状重建(worldview/affect/language7/color),
     这样 /cat/exhibit 的投影逻辑对 demo 幅与正式库幅完全一致。
幂等:按 source_batch='demo:gallery226' 先清后插,可反复重跑。
跑:  python3 ingest_demo226.py
"""
import os, json, psycopg2

GALLERY = "/home/ubuntu/users/qiuyiwu/aha-art-demo/data/gallery_works.json"
SRC = "demo:gallery226"
# museum 短轴名 → DB language7 长名(catalog_api._L7MAP 的反向)
L7_LONG = {"构图": "构图与组织", "空间": "透视与空间", "造型": "形状与造型",
           "光影": "光影与明暗", "色彩": "色彩系统", "笔触": "笔触与肌理", "边缘": "边缘与节奏"}


def slug_of(aid, artist):
    if aid and aid.startswith("ARTIST."):
        return aid.split(".", 1)[1]
    return (aid or artist or "anon").replace(" ", "_").lower()


def build_vlm(w):
    """把 gallery_works 的扁平字段重建成 DB vlm 形状(供 /cat/exhibit 投影)。"""
    vlm = {"_src": SRC}
    if w.get("x") is not None and w.get("y") is not None:
        vlm["worldview"] = {"x": w["x"], "y": w["y"], "wv": w.get("wv")}
    vad = w.get("vad") or {}
    af = {}
    if vad:
        af["vad"] = {"valence": vad.get("v"), "arousal": vad.get("a"), "dominance": vad.get("d")}
    if w.get("emo"):
        af["primary_anchor"] = w["emo"]
    if af:
        vlm["affect"] = af
    lang = w.get("lang") or {}
    if lang:
        vlm["language7"] = {L7_LONG[k]: {"v": v} for k, v in lang.items() if k in L7_LONG}
    if w.get("color"):
        vlm["color"] = w["color"]
    return vlm


def main():
    works = json.load(open(GALLERY))["works"]
    cfg = json.load(open(os.path.expanduser("~/.aha_pg.json")))
    cn = psycopg2.connect(host=cfg["host"], port=cfg["port"], dbname=cfg["dbname"],
                          user=cfg["user"], password=cfg["password"])
    cur = cn.cursor()

    # --- 幂等清理(注意 works↔files 循环 FK,先断 primary_file_id) ---
    cur.execute("UPDATE works SET primary_file_id=NULL WHERE source_batch=%s", (SRC,))
    cur.execute("DELETE FROM files WHERE work_id IN (SELECT work_id FROM works WHERE source_batch=%s)", (SRC,))
    cur.execute("DELETE FROM works WHERE source_batch=%s", (SRC,))
    cur.execute("DELETE FROM artists WHERE artist_id LIKE 'demo:%' "
                "AND artist_id NOT IN (SELECT DISTINCT artist_id FROM works WHERE artist_id IS NOT NULL)")
    cn.commit()

    n_art, n_work = 0, 0
    seen_artist = set()
    for w in works:
        aid = "demo:" + slug_of(w.get("aid"), w.get("artist"))
        if aid not in seen_artist:
            cur.execute(
                """INSERT INTO artists(artist_id,name_cn,region) VALUES(%s,%s,%s)
                   ON CONFLICT(artist_id) DO UPDATE SET name_cn=EXCLUDED.name_cn,
                     region=COALESCE(artists.region,EXCLUDED.region)""",
                (aid, w.get("artist") or "佚名", w.get("region")))
            seen_artist.add(aid)
            n_art += 1
        vlm = build_vlm(w)
        cur.execute(
            """INSERT INTO works(title,artist_id,year,status,is_artwork,quality,
                                 source_batch,vlm,exhibited,exhibit_at,reviewed_at)
               VALUES(%s,%s,%s,'kept',true,0.7,%s,%s,true,now(),now()) RETURNING work_id""",
            (w.get("title") or "无题", aid, str(w.get("year") or ""), SRC, json.dumps(vlm, ensure_ascii=False)))
        wid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO files(work_id,cos_key,source_batch) VALUES(%s,%s,%s) RETURNING file_id",
            (wid, w["file"], SRC))
        fid = cur.fetchone()[0]
        cur.execute("UPDATE works SET primary_file_id=%s WHERE work_id=%s", (fid, wid))
        n_work += 1

    cn.commit()
    cur.execute("SELECT count(*) FROM works WHERE source_batch=%s AND exhibited", (SRC,))
    total = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM works WHERE source_batch=%s AND vlm ? 'worldview'", (SRC,))
    ready = cur.fetchone()[0]
    cn.close()
    print(f"入库完成:artists +{n_art} · works {n_work} · exhibited {total} · 有世界观坐标 {ready}")


if __name__ == "__main__":
    main()
