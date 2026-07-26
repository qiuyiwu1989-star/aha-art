#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据关联聚合:从 v_ledger + artists 算每位规范艺术家的【主流派/流派分布/生卒/年代/出生地/东西】。
写 artist_assoc 表(纯派生,可重算,不 ALTER 大表)。供 艺术家→流派、流派→艺术家、时间线、地域 等关联。"""
import json, psycopg2
from psycopg2.extras import execute_values, Json
d=json.load(open('/home/ubuntu/.aha_pg.json'))
con=psycopg2.connect(host=d['host'],port=d['port'],dbname=d['dbname'],user=d['user'],password=d['password']);cur=con.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS artist_assoc(
  artist_id text PRIMARY KEY, name_cn text, name_en text,
  n_works int, primary_style int, primary_style_cn text, styles jsonb,
  born int, death int, era text, region text, east_west text, computed_at timestamptz DEFAULT now())""")
con.commit()

# 1) 每位规范艺术家 × 规范流派 的作品数
cur.execute("""SELECT canonical_artist_id aid, style_canon_id sid, max(style_canon) scn, count(*) n
  FROM v_ledger WHERE canonical_artist_id IS NOT NULL AND canonical_artist_id NOT LIKE '%unknown%'
  GROUP BY canonical_artist_id, style_canon_id""")
from collections import defaultdict
A=defaultdict(lambda:{"n":0,"styles":[]})
for aid,sid,scn,n in cur.fetchall():
    A[aid]["n"]+=n
    if sid is not None and sid!=0:
        A[aid]["styles"].append({"canon_id":sid,"name":scn,"n":n})
# 2) 艺术家基础(规范=canonical_artist_id is null 的那批,取其 born/death/region/east_west)
cur.execute("""SELECT artist_id,name_cn,name_en,born,death,region,east_west FROM artists""")
AB={r[0]:r[1:] for r in cur.fetchall()}
def era_of(born):
    if not born: return None
    c=(born//100)+1
    return f"{c}世纪" if c>0 else "古代"

rows=[]
for aid,v in A.items():
    base=AB.get(aid) or (None,)*6
    styles=sorted(v["styles"],key=lambda x:-x["n"])
    ps=styles[0] if styles else None
    rows.append((aid, base[0], base[1], v["n"], ps["canon_id"] if ps else None,
                 ps["name"] if ps else None, Json(styles[:6]),
                 base[2], base[3], era_of(base[2]), base[4], base[5]))
cur.execute("TRUNCATE artist_assoc")
execute_values(cur,"""INSERT INTO artist_assoc(artist_id,name_cn,name_en,n_works,primary_style,primary_style_cn,styles,born,death,era,region,east_west) VALUES %s""",rows,page_size=2000)
con.commit()
print(f"artist_assoc 写入 {len(rows):,} 位规范艺术家")
cur.execute("SELECT primary_style_cn,count(*) FROM artist_assoc WHERE primary_style_cn IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 10")
print("主流派分布(艺术家数):",[(r[0],r[1]) for r in cur.fetchall()])
cur.execute("SELECT count(*) FILTER(WHERE primary_style IS NOT NULL), count(*) FILTER(WHERE born IS NOT NULL), count(*) FILTER(WHERE region IS NOT NULL AND region<>'') FROM artist_assoc")
r=cur.fetchone(); print(f"覆盖: 有主流派 {r[0]:,} | 有生卒 {r[1]:,} | 有出生地 {r[2]:,}")
cur.execute("SELECT name_cn,n_works,primary_style_cn,born,death,region FROM artist_assoc WHERE born IS NOT NULL AND primary_style_cn IS NOT NULL ORDER BY n_works DESC LIMIT 6")
print("样例(作品多的):");
for r in cur.fetchall(): print(f"  {r[0]} · {r[1]}件 · {r[2]} · {r[3]}-{r[4]} · {r[5]}")
