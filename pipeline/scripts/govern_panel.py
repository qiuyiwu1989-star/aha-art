#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 dashboard 治理面板数据 governance.json:总账概况 + 艺术家归并 + VLM优质待处理队列。"""
import json, datetime, psycopg2
d=json.load(open('/home/ubuntu/.aha_pg.json'))
c=psycopg2.connect(host=d['host'],port=d['port'],dbname=d['dbname'],user=d['user'],password=d['password']).cursor()
def q(s,a=None):c.execute(s,a);return c.fetchall()
def one(s):c.execute(s);return c.fetchone()

# 1) 总账 v_ledger
ledger_total=one("select count(*) from v_ledger")[0]
by_src=[{"src":r[0],"rows":r[1],"completeness":float(r[2]),"has_title":r[3]} for r in q(
  "select source,count(*),round(avg(meta_score)::numeric,3),count(title) from v_ledger group by 1 order by 2 desc")]
ew={r[0]:r[1] for r in q("select coalesce(east_west,'未定'),count(*) from v_ledger group by 1")}

# 2) 艺术家归并
art=one("""select count(*) src, count(*) filter(where canonical_artist_id is null) canon,
  count(*) filter(where canonical_artist_id is not null) merged, count(*) filter(where aha_kg_id is not null) kg from artists""")
alias=one("select count(*) from artist_alias")[0]
top_merge=[{"name":r[0],"ids":r[1]} for r in q("""select coalesce(name_cn,name_en),count(*) n from artists
  where canonical_artist_id is not null group by canonical_artist_id,coalesce(name_cn,name_en) order by 2 desc limit 6""")]

# 3) VLM 优质待处理队列 = pending + canonical + 高清/中清 + 非占位 + 非小图
vlm_ready=[{"src":r[0],"ready":r[1],"pending":r[2]} for r in q("""
  select split_part(w.source_batch,':',1) s,
    count(*) filter(where g.dedup_role='canonical' and g.res_tier in('hd','mid') and not g.is_placeholder and not g.is_tiny) ready,
    count(*) pending
  from works w join work_governance g on g.work_id=w.work_id
  where w.status='pending' group by 1 order by 3 desc""")]
ready_total=sum(x["ready"] for x in vlm_ready)
pending_total=sum(x["pending"] for x in vlm_ready)

# 4) 治理质量
gov=one("""select count(*) filter(where is_placeholder),count(*) filter(where is_tiny),
  count(*) filter(where dedup_role='dup'),(select count(*) from work_canonical_meta where trusted=false) from work_governance""")

out={"updated":datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
 "ledger":{"total":ledger_total,"by_source":by_src,"east_west":ew},
 "artists":{"source":art[0],"canonical":art[1],"merged":art[2],"curated_aligned":art[3],"aliases":alias,"top_merge":top_merge},
 "vlm_queue":{"ready_total":ready_total,"pending_total":pending_total,"by_source":vlm_ready},
 "quality":{"placeholder":gov[0],"tiny":gov[1],"dup":gov[2],"untrusted_clusters":gov[3]}}
for p in ["/home/ubuntu/users/qiuyiwu/aha-art/web/data/governance.json","/data/pub/p/aha/data/governance.json"]:
    import os;os.makedirs(os.path.dirname(p),exist_ok=True);json.dump(out,open(p,"w"),ensure_ascii=False,indent=1)
print("写 governance.json")
print(f"  总账 {ledger_total:,} | 规范艺术家 {art[1]:,}(归并{art[2]:,}) | VLM优质待处理 {ready_total:,}/{pending_total:,}")
print(f"  east/west {ew} | 占位{gov[0]} 假簇{gov[3]}")
