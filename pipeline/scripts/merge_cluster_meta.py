#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""簇内元数据合并:把同一幅画各源最佳元数据回填到簇主图(尤其给 yishujia 高清裸图借标)。
带假簇闸门(≥3标题且≥3画家→untrusted不合并,防phash撞车污染)。纯派生表,可重算。"""
import json, re, unicodedata, psycopg2
from psycopg2.extras import execute_values
d=json.load(open('/home/ubuntu/.aha_pg.json'))
con=psycopg2.connect(host=d['host'],port=d['port'],dbname=d['dbname'],user=d['user'],password=d['password']);cur=con.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS work_canonical_meta(
  work_id bigint PRIMARY KEY, title text,title_src text, artist_id text,artist_src text,
  year text,year_src text, school text,school_src text, medium text,medium_src text,
  n_members int, trusted boolean, merged_at timestamptz DEFAULT now());""")
con.commit()

def nt(s): return re.sub(r'[^a-z0-9一-鿿]','',unicodedata.normalize('NFKD',(s or '')).encode('ascii','ignore').decode().lower()) if s and s.isascii() else re.sub(r'\s','',(s or ''))
SRCW={'yh':4,'nbfox':3,'wikiart':2,'yishujia':1}
def srcof(sb):
    return sb.split(':')[0] if sb else ''

# 1) 所有簇
cur.execute("select cluster_id,work_id,member_file_ids from dup_clusters where work_id is not null")
clusters=cur.fetchall()
allf=set()
for _,_,fids in clusters:
    if fids: allf.update(fids)
# 2) file_id → work_id
cur.execute("select file_id,work_id from files where file_id=any(%s)",(list(allf),))
f2w={f:w for f,w in cur.fetchall()}
# 3) 涉及 work 的元数据(artist 取归并后规范)
allw=set(f2w.values())|{c[1] for c in clusters}
cur.execute("""select w.work_id,w.title,coalesce(a.canonical_artist_id,w.artist_id),
  w.year,w.school,w.medium,split_part(w.source_batch,':',1)
  from works w left join artists a on a.artist_id=w.artist_id where w.work_id=any(%s)""",(list(allw),))
WM={r[0]:r[1:] for r in cur.fetchall()}   # work_id -> (title,artist_canon,year,school,medium,src)
def real_artist(aid): return aid and 'unknown' not in aid

rows=[]; n_trust=n_untrust=0; n_yh_borrow=0
for cid,surv,fids in clusters:
    works=set()
    for f in (fids or []):
        if f in f2w: works.add(f2w[f])
    works.add(surv)
    mem=[WM[w] for w in works if w in WM]
    if not mem: continue
    titles={nt(m[0]) for m in mem if m[0]}
    artists={m[1] for m in mem if real_artist(m[1])}
    trusted = not(len(titles)>=3 and len(artists)>=3)
    if trusted: n_trust+=1
    else: n_untrust+=1
    def best(field_i):
        cand=[m for m in mem if m[field_i]]
        if not cand: return (None,None)
        m=max(cand,key=lambda x:(SRCW.get(x[5],0), len(str(x[field_i]))))
        return (m[field_i], m[5])
    if trusted:
        ti,ts=best(0)
        ar = next((m[1] for m in sorted(mem,key=lambda x:-SRCW.get(x[5],0)) if real_artist(m[1])),None)
        asrc=next((m[5] for m in sorted(mem,key=lambda x:-SRCW.get(x[5],0)) if real_artist(m[1])),None)
        yi,ysr=best(2); sc,scr=best(3); me,mer=best(4)
        # 统计 yishujia 主图借到标题
        sv=WM.get(surv)
        if sv and sv[5]=='yishujia' and ti: n_yh_borrow+=1
        rows.append((surv,ti,ts,ar,asrc,yi,ysr,sc,scr,me,mer,len(mem),True))
    else:
        rows.append((surv,None,None,None,None,None,None,None,None,None,None,len(mem),False))

cur.execute("TRUNCATE work_canonical_meta")
execute_values(cur,"""insert into work_canonical_meta(work_id,title,title_src,artist_id,artist_src,year,year_src,school,school_src,medium,medium_src,n_members,trusted) values %s on conflict(work_id) do nothing""",rows,page_size=2000)
con.commit()
print(f"簇 {len(clusters):,} → 合并 {len(rows):,} 行 (trusted {n_trust:,} / untrusted假簇 {n_untrust:,})")
print(f"  yishujia 高清主图借到标题: {n_yh_borrow:,}")
cur.execute("select count(*) from work_canonical_meta cm join works w on w.work_id=cm.work_id where w.source_batch like 'yishujia%' and cm.title is not null")
print(f"  核验 yishujia 主图有标题: {cur.fetchone()[0]:,}")
cur.execute("select w.title,cm.title,cm.artist_id from work_canonical_meta cm join works w on w.work_id=cm.work_id where w.source_batch like 'yishujia%' and cm.title is not null limit 3")
for r in cur.fetchall(): print("    原[",r[0],"] → 借得[",r[1],"] /",r[2])
