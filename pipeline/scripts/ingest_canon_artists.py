#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把策展考据 kg_artists.json(282 位,ARTIST.* + 中英文 + 生卒/世界观/师承/bio…)写进库,
并把管线碎片化的来源艺术家(nbfox/wikiart/yh)按中英文名匹配到 canon,中英文就此对应。

- artists_canon: canon_id(ARTIST.*) + cn/en/born/death/region/nationality + lore(全考据 jsonb)
- artists.aha_kg_id: 来源艺术家 → 匹配到的 canon_id(本就是为对齐这套设计的字段)
匹配键:规范化英文名(主) + 中文名(辅)。幂等。
用法: python3 ingest_canon_artists.py [--json /data/pub/p/aha/data/kg_artists.json]
"""
import os, re, json, sys, argparse, unicodedata
import psycopg2

def pg():
    d = json.load(open(os.path.expanduser("~/.aha_pg.json")))
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

def norm_en(s):
    if not s: return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()
def norm_cn(s):
    if not s: return ""
    return re.sub(r"的(浮世绘|油画|作品|画|素描|版画).*$", "", str(s).strip())
def _yr(x):
    m = re.search(r"(\d{3,4})", str(x or "")); return int(m.group(1)) if m else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="/data/pub/p/aha/data/kg_artists.json")
    a = ap.parse_args()
    cn = pg(); cur = cn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS artists_canon(
        canon_id text PRIMARY KEY, cn text, en text, born int, death int,
        region text, nationality text, lore jsonb)""")
    cur.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS aha_kg_id text")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_artists_kg ON artists(aha_kg_id)")

    data = json.load(open(a.json)); arts = data.get("artists", data)
    items = list(arts.items()) if isinstance(arts, dict) else [(x.get("id"), x) for x in arts]
    # 头像不在 kg_artists.json,而在同目录 kg_artist_portraits.json;灌库时合并进 lore,
    # 否则每次重灌都会把 DB 里已有的 portrait 字段覆盖丢(踩过这个坑)。
    PORT = {}
    ppath = os.path.join(os.path.dirname(os.path.abspath(a.json)), "kg_artist_portraits.json")
    if os.path.isfile(ppath):
        PORT = json.load(open(ppath))
        print(f"  合并头像 {sum(1 for x in PORT.values() if x.get('file'))} 张")
    for cid, v in items:
        if cid in PORT and PORT[cid].get("file"):
            v = dict(v); v["portrait"] = PORT[cid]["file"]; v["portrait_src"] = PORT[cid].get("source")
        cur.execute("""INSERT INTO artists_canon(canon_id,cn,en,born,death,region,nationality,lore)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (canon_id) DO UPDATE SET
            cn=EXCLUDED.cn,en=EXCLUDED.en,born=EXCLUDED.born,death=EXCLUDED.death,
            region=EXCLUDED.region,nationality=EXCLUDED.nationality,lore=EXCLUDED.lore""",
            (cid, v.get("cn"), v.get("en"), _yr(v.get("born")), _yr(v.get("death")),
             v.get("region"), v.get("nationality"), json.dumps(v, ensure_ascii=False)))
    cn.commit()
    print(f"✓ artists_canon 写入 {len(items)} 位考据艺术家")

    # 建匹配索引
    by_en, by_cn = {}, {}
    for cid, v in items:
        if v.get("en"): by_en.setdefault(norm_en(v["en"]), cid)
        if v.get("cn"): by_cn.setdefault(str(v["cn"]).strip(), cid)

    # 来源艺术家 → canon
    cur.execute("SELECT artist_id, name_cn, name_en FROM artists")
    src = cur.fetchall()
    n_en = n_cn = 0; updates = []
    for aid, ncn, nen in src:
        if aid.startswith("ARTIST."): continue
        cid = None
        # 英文名:直接 name_en,或从 slug(冒号后)反推
        cand_en = nen or (aid.split(":", 1)[1].replace("-", " ") if ":" in aid else "")
        if cand_en and norm_en(cand_en) in by_en:
            cid = by_en[norm_en(cand_en)]; n_en += 1
        elif ncn and norm_cn(ncn) in by_cn:
            cid = by_cn[norm_cn(ncn)]; n_cn += 1
        if cid: updates.append((cid, aid))
    cur.executemany("UPDATE artists SET aha_kg_id=%s WHERE artist_id=%s", updates)
    cn.commit()
    print(f"✓ 来源艺术家匹配到 canon: {len(updates)} 位(英文名 {n_en} + 中文名 {n_cn}) / 共 {len(src)}")
    # 覆盖:有多少 canon 被命中、命中的 canon 覆盖多少作品
    cur.execute("SELECT count(DISTINCT aha_kg_id) FROM artists WHERE aha_kg_id IS NOT NULL")
    print(f"  命中 canon 身份 {cur.fetchone()[0]} / 282")
    cur.execute("SELECT count(*) FROM works w JOIN artists a ON a.artist_id=w.artist_id WHERE a.aha_kg_id IS NOT NULL AND w.status='kept'")
    print(f"  这些 canon 覆盖核心资产作品 {cur.fetchone()[0]}")
    cn.close()

if __name__ == "__main__":
    main()
