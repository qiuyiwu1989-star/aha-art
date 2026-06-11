#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""治理质量标记:给每件作品算分辨率档/小图/占位/元数据完整度/来源覆盖/去重角色,写 work_governance。
纯库内SQL口径,快;给下游VLM筛选用。可重算。"""
import json, psycopg2
from psycopg2.extras import execute_values
d=json.load(open('/home/ubuntu/.aha_pg.json'))
con=psycopg2.connect(host=d['host'],port=d['port'],dbname=d['dbname'],user=d['user'],password=d['password']);cur=con.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS work_governance(
  work_id bigint PRIMARY KEY, res_tier text, px bigint, is_tiny boolean,
  is_placeholder boolean, meta_score real, n_sources int, dedup_role text,
  cluster_id bigint, trusted_merge boolean, computed_at timestamptz DEFAULT now());""")
con.commit()

# 1) 簇派生:work→cluster_id / n_sources / 占位(untrusted簇全员)
cur.execute("select cluster_id,work_id,member_file_ids from dup_clusters where work_id is not null")
clusters=cur.fetchall()
allf=set()
for _,_,fids in clusters:
    if fids: allf.update(fids)
cur.execute("select file_id,work_id from files where file_id=any(%s)",(list(allf),))
f2w=dict(cur.fetchall())
cur.execute("select work_id from work_canonical_meta where trusted=false")
untrusted_surv={r[0] for r in cur.fetchall()}
cur.execute("select work_id,split_part(source_batch,':',1) from works")
w2src=dict(cur.fetchall())
w_cluster={}; w_nsrc={}; w_placeholder={}
for cid,surv,fids in clusters:
    works={surv}|{f2w[f] for f in (fids or []) if f in f2w}
    srcs={w2src.get(w) for w in works}
    ph = surv in untrusted_surv
    for w in works:
        w_cluster[w]=cid; w_nsrc[w]=len(srcs)
        if ph: w_placeholder[w]=True

# 2) 每件基础:主图 wh/bytes + 合并后元数据完整度
cur.execute("""select w.work_id, w.status, coalesce(f.width,0)*coalesce(f.height,0) px, coalesce(f.bytes,0) by,
  coalesce(cm.title,w.title) t, coalesce(cm.year,w.year) y, coalesce(cm.school,w.school) sc,
  coalesce(cm.medium,w.medium) me, coalesce(cm.artist_id,a.canonical_artist_id,w.artist_id) aid
  from works w join files f on f.file_id=w.primary_file_id
  left join work_canonical_meta cm on cm.work_id=w.work_id
  left join artists a on a.artist_id=w.artist_id""")
rows=[]
for wid,status,px,by,t,y,sc,me,aid in cur.fetchall():
    tier='hd' if px>=2_000_000 else ('mid' if px>=200_000 else 'thumb')
    ms=sum(1 for x in (t,y,sc,me) if x)/5.0 + (0.2 if aid and 'unknown' not in aid else 0)
    rows.append((wid, tier, px, by<15360, bool(w_placeholder.get(wid,False)),
                 round(min(ms,1.0),3), w_nsrc.get(wid,1),
                 'dup' if status=='dup' else 'canonical', w_cluster.get(wid),
                 (wid not in untrusted_surv) if wid in w_cluster else None))
cur.execute("TRUNCATE work_governance")
execute_values(cur,"""insert into work_governance(work_id,res_tier,px,is_tiny,is_placeholder,meta_score,n_sources,dedup_role,cluster_id,trusted_merge) values %s""",rows,page_size=5000)
con.commit()

print(f"work_governance 写入 {len(rows):,} 行")
cur.execute("select res_tier,count(*) from work_governance group by 1 order by 2 desc")
print("  分辨率档:",{r[0]:r[1] for r in cur.fetchall()})
cur.execute("select count(*) filter(where is_placeholder),count(*) filter(where is_tiny),count(*) filter(where dedup_role='dup') from work_governance")
r=cur.fetchone(); print(f"  占位 {r[0]:,} | 小图 {r[1]:,} | dup {r[2]:,}")
cur.execute("select round(avg(meta_score)::numeric,3) from work_governance"); print("  平均元数据完整度:",cur.fetchone()[0])
