#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""艺术家身份归并:6463 个源 artist → 规范身份(并查集)。不重指 works,只加映射列+别名表。
键:norm_en(name_en) 或 name_cn 相等。代表=权威rank高者。curated命中写 aha_kg_id。幂等可重跑。"""
import json, re, unicodedata, psycopg2
from psycopg2.extras import execute_values

d=json.load(open('/home/ubuntu/.aha_pg.json'))
con=psycopg2.connect(host=d['host'],port=d['port'],dbname=d['dbname'],user=d['user'],password=d['password']);cur=con.cursor()

cur.execute("""ALTER TABLE artists ADD COLUMN IF NOT EXISTS canonical_artist_id text;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS merge_reason text;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS merge_confidence real;
CREATE INDEX IF NOT EXISTS idx_artists_canon ON artists(canonical_artist_id);""")
con.commit()

def norm_en(s):
    if not s: return ""
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode()
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',s.lower())).strip()
def norm_cn(s):
    if not s: return ""
    return re.sub(r'\s+','',s).strip()

cur.execute("select artist_id,name_cn,name_en,born,death,nationality,region from artists")
A=cur.fetchall()
idx={a[0]:i for i,a in enumerate(A)}
parent=list(range(len(A)))
def find(x):
    while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
    return x
def union(a,b):
    ra,rb=find(a),find(b)
    if ra!=rb: parent[max(ra,rb)]=min(ra,rb)

# 按强键聚合
by_en={}; by_cn={}
for i,a in enumerate(A):
    ne=norm_en(a[2])
    if len(ne)>=3: by_en.setdefault(ne,[]).append(i)
    nc=norm_cn(a[1])
    # 跳过把英文塞进中文名的脏数据(name_cn==name_en)
    if len(nc)>=2 and nc!=norm_cn(a[2]): by_cn.setdefault(nc,[]).append(i)
for grp in list(by_en.values())+list(by_cn.values()):
    for j in grp[1:]: union(grp[0],j)

# 权威 rank:源 + 数据丰富度
def src_rank(aid):
    if aid.startswith('yh:name:'): return 1
    if aid.startswith('yh:'): return 3
    if aid.startswith('nbfox:'): return 2
    if aid.startswith('wikiart:'): return 1
    return 0
def rich(a): return sum(1 for x in (a[1],a[3],a[4],a[5],a[6]) if x)
def keyf(i):
    a=A[i]; return (src_rank(a[0]), rich(a), a[0])  # 大者优先;a[0]兜底确定性

# curated 名字索引(中/英 → canon_id)
cur.execute("select canon_id,cn,en from artists_canon")
canon={}
for cid,cn,en in cur.fetchall():
    if cn: canon[norm_cn(cn)]=cid
    if en: canon[norm_en(en)]=cid

groups={}
for i in range(len(A)): groups.setdefault(find(i),[]).append(i)

upd=[]; aliases=[]; kgupd=[]
n_merged=0; n_groups_multi=0
for root,members in groups.items():
    rep=max(members,key=keyf)            # 代表
    rep_id=A[rep][0]
    if len(members)>1: n_groups_multi+=1
    # curated 命中 → 给代表写 aha_kg_id
    cid=None
    for m in members:
        a=A[m]
        cid=canon.get(norm_en(a[2])) or canon.get(norm_cn(a[1]))
        if cid: break
    if cid: kgupd.append((cid,rep_id))
    for m in members:
        a=A[m]
        if m==rep:
            upd.append((None,'self',1.0,a[0]))   # 代表:canonical=NULL
        else:
            reason='name_en' if norm_en(a[2]) and norm_en(a[2])==norm_en(A[rep][2]) else 'name_cn'
            upd.append((rep_id,reason,1.0,a[0])); n_merged+=1
            for nm in (a[1],a[2]):
                if nm and nm.strip(): aliases.append((nm.strip(),rep_id))

execute_values(cur,"update artists set canonical_artist_id=v.c,merge_reason=v.r,merge_confidence=v.f from (values %s) v(c,r,f,aid) where artists.artist_id=v.aid",upd,page_size=2000)
if kgupd: execute_values(cur,"update artists set aha_kg_id=v.k from (values %s) v(k,aid) where artists.artist_id=v.aid",kgupd,page_size=2000)
if aliases: execute_values(cur,"insert into artist_alias(alias,artist_id) values %s on conflict(alias) do nothing",list(set(aliases)),page_size=2000)
con.commit()

cur.execute("select count(*) filter(where canonical_artist_id is null) canon, count(*) total, count(*) filter(where aha_kg_id is not null) kg from artists")
r=cur.fetchone()
print(f"源艺术家 {r[1]:,} → 规范身份 {r[0]:,}（归并掉 {n_merged:,}，{n_groups_multi:,} 个多人组）")
print(f"  curated 对齐(aha_kg_id) {r[2]:,} | artist_alias {len(set(aliases)):,} 条")
cur.execute("select artist_id,canonical_artist_id from artists where lower(name_en) like 'franz xaver winterhalter'")
print("  验证 Winterhalter 4 id:");
for x in cur.fetchall(): print("    ",x[0],"→",x[1] or "(自己是规范)")
