#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一总账 v_ledger:每幅唯一画一行(主图+合并元数据+规范艺术家+治理标记),供下游VLM消费。
建/刷视图;--jsonl 额外导出 web/data/ledger.jsonl。可重跑。"""
import json, sys, psycopg2
d=json.load(open('/home/ubuntu/.aha_pg.json'))
con=psycopg2.connect(host=d['host'],port=d['port'],dbname=d['dbname'],user=d['user'],password=d['password']);cur=con.cursor()

# v_ledger 唯一权威定义(优先级: 人工编辑 work_edit > 清洗标题 title_clean > 簇合并 cm > 原值)
cur.execute("DROP VIEW IF EXISTS v_ledger")
cur.execute("""
CREATE VIEW v_ledger AS
SELECT w.work_id, f.cos_key,
  COALESCE(we.title, w.title_clean, cm.title, w.title) AS title,
  COALESCE(we.year, cm.year, w.year) AS year,
  COALESCE(we.school, cm.school, w.school) AS school,
  sc.name_cn AS style_canon, sc.canon_id AS style_canon_id,
  COALESCE(we.medium, cm.medium, w.medium) AS medium,
  COALESCE(we.artist_id, cm.artist_id, ca.canonical_artist_id, w.artist_id) AS canonical_artist_id,
  ar.name_cn, ar.name_en, ar.aha_kg_id, ar.region AS artist_region, COALESCE(ar.east_west, cn.region) AS east_west,
  split_part(w.source_batch,':',1) AS source,
  g.n_sources, g.res_tier, g.px, g.meta_score, g.is_tiny, g.is_placeholder,
  g.trusted_merge, g.dedup_role, g.cluster_id,
  w.status, (w.vlm IS NOT NULL) AS has_vlm,
  (SELECT array_agg(s.subject) FROM work_subjects s WHERE s.work_id=w.work_id) AS subjects,
  (we.work_id IS NOT NULL) AS edited
FROM works w
JOIN files f ON f.file_id = w.primary_file_id
LEFT JOIN work_edit we ON we.work_id = w.work_id
LEFT JOIN work_canonical_meta cm ON cm.work_id = w.work_id
LEFT JOIN work_governance     g  ON g.work_id  = w.work_id
LEFT JOIN artists ca ON ca.artist_id = w.artist_id
LEFT JOIN artists ar ON ar.artist_id = COALESCE(we.artist_id, cm.artist_id, ca.canonical_artist_id, w.artist_id)
LEFT JOIN artists_canon cn ON cn.canon_id = ar.aha_kg_id
LEFT JOIN style_map sm ON sm.raw = COALESCE(we.school, cm.school, w.school)
LEFT JOIN style_canon sc ON sc.canon_id = sm.canon_id
WHERE w.status <> 'dup';
""")
con.commit()
print("✓ 视图 v_ledger 已建/刷(含 work_edit 编辑覆盖层)")

cur.execute("select count(*) from v_ledger"); n=cur.fetchone()[0]
print(f"总账行数 {n:,}（=非dup作品）")
cur.execute("select count(*) from v_ledger where cos_key is null"); print(f"  主图缺失(应0): {cur.fetchone()[0]}")
cur.execute("select source,count(*),round(avg(meta_score)::numeric,3),count(*) filter(where title is not null) from v_ledger group by 1 order by 2 desc")
print("  各来源 / 行数 / 平均完整度 / 有标题:")
for r in cur.fetchall(): print(f"    {r[0]:9} {r[1]:>7,}  {r[2]}  标题{r[3]:,}")
cur.execute("select east_west,count(*) from v_ledger where east_west is not null group by 1")
print("  东西(curated对齐部分):",{r[0]:r[1] for r in cur.fetchall()})

if '--jsonl' in sys.argv:
    import os
    out="/home/ubuntu/users/qiuyiwu/aha-art/web/data/ledger.jsonl"
    cur.execute("select * from v_ledger")
    cols=[c[0] for c in cur.description]
    n=0
    with open(out,'w') as fp:
        for row in cur:
            fp.write(json.dumps(dict(zip(cols,row)),ensure_ascii=False,default=str)+"\n"); n+=1
    print(f"✓ 导出 {out}  {n:,} 行")
