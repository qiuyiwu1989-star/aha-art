#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""加法式迁移:202 富节点 → 新表 style_nodes,canonical 外键指回 styles(32)。
不触碰 works 的 11.8 万挂钩。可 DROP TABLE style_nodes 回滚。"""
import json, os, psycopg2
from psycopg2.extras import Json

NODES=json.load(open('/data/pub/p/aha/data/kg_style.json'))['nodes']
BR={r['id']:r for r in json.load(open('/data/pub/p/aha/data/kg_style_canonical.json'))['map']}

d=json.load(open(os.path.expanduser("~/.aha_pg.json")))
cn=psycopg2.connect(host=d["host"],port=d["port"],dbname=d["dbname"],user=d["user"],password=d["password"])
cur=cn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS style_nodes(
  style_id        text PRIMARY KEY,           -- STYLE.west.015
  cn              text NOT NULL,
  region          text,                        -- east/west
  wv              text,                        -- 世界观区 WV1..6
  xi              text,                        -- 体系
  year            int,
  conf            text,                        -- high / low(待核对)
  def_src         text,                        -- authored / derived
  canonical       text REFERENCES styles(style_id),  -- ← 桥:32 标准码
  eastern_lineage text,                        -- 东方子谱系(西方为 NULL)
  bridge_conf     text,                        -- rule / inferred / manual ...
  aka             jsonb DEFAULT '[]',
  coord           jsonb,
  lore            jsonb,
  data            jsonb,                        -- 整个原节点,零丢失
  sort            int
)""")
cur.execute("CREATE INDEX IF NOT EXISTS idx_style_nodes_canon  ON style_nodes(canonical)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_style_nodes_region ON style_nodes(region)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_style_nodes_wv     ON style_nodes(wv)")

def yi(v):
    try: return int(v)
    except: return None

up=0
for i,x in enumerate(NODES):
    b=BR.get(x['id'],{})
    cur.execute("""INSERT INTO style_nodes
      (style_id,cn,region,wv,xi,year,conf,def_src,canonical,eastern_lineage,bridge_conf,aka,coord,lore,data,sort)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT (style_id) DO UPDATE SET
        cn=EXCLUDED.cn,region=EXCLUDED.region,wv=EXCLUDED.wv,xi=EXCLUDED.xi,year=EXCLUDED.year,
        conf=EXCLUDED.conf,def_src=EXCLUDED.def_src,canonical=EXCLUDED.canonical,
        eastern_lineage=EXCLUDED.eastern_lineage,bridge_conf=EXCLUDED.bridge_conf,
        aka=EXCLUDED.aka,coord=EXCLUDED.coord,lore=EXCLUDED.lore,data=EXCLUDED.data,sort=EXCLUDED.sort""",
      (x['id'],x['cn'],x.get('region'),x.get('wv'),x.get('xi'),yi(x.get('year')),
       x.get('conf'),x.get('def_src'),b.get('canonical'),b.get('eastern_lineage'),b.get('bridge_conf'),
       Json(x.get('aka') or []),Json(x.get('coord')),Json(x.get('lore')),Json(x),i))
    up+=1
cn.commit()
cur.execute("SELECT count(*) FROM style_nodes"); print("style_nodes 行数:", cur.fetchone()[0])
cur.execute("SELECT region,count(*) FROM style_nodes GROUP BY region"); print("按区:", dict(cur.fetchall()))
# 外键完整性
cur.execute("SELECT count(*) FROM style_nodes s LEFT JOIN styles c ON s.canonical=c.style_id WHERE s.canonical IS NOT NULL AND c.style_id IS NULL")
print("外键孤儿(应0):", cur.fetchone()[0])
cn.close()
