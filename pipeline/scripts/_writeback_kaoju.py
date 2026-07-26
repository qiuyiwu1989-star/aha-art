#!/usr/bin/env python3
"""考据结果写回 style_nodes。严格:仅 upgrade+核验confirmed 升 authored;
其余富化内容但保持 low(附待校点);delete/merge 只打标记不动结构(待用户裁决)。先备份。可回滚。"""
import json, psycopg2
d=json.load(open('_kaoju_output.json'))
cfg=json.load(open('/home/ubuntu/.aha_pg.json'))
conn=psycopg2.connect(host=cfg['host'],port=cfg['port'],dbname=cfg['dbname'],user=cfg['user'],password=cfg['password'])
cur=conn.cursor()
# 备份(幂等:存在则跳过)
cur.execute("CREATE TABLE IF NOT EXISTS style_nodes_bak_20260613 AS TABLE style_nodes")
conn.commit()

def setif(dct,k,v):
    if v not in (None,'',[],{}): dct[k]=v

stats={'authored':0,'enriched_low':0,'flagged_delete':0,'flagged_merge':0}
for r in d:
    _id=r['node']; kj=r['kaoju']; vf=r.get('verify') or {}
    rec=vf.get('final_recommend') or kj.get('recommend')
    cur.execute("select data from style_nodes where style_id=%s",(_id,))
    row=cur.fetchone()
    if not row: continue
    data=row[0] or {}; lore=data.get('lore') or {}
    setif(data,'def',kj.get('def')); setif(data,'desc',kj.get('essence') or kj.get('def'))
    for k in ('period','origin','people','motifs','parents','influences','against','works_named','essence'):
        setif(lore,k,kj.get(k))
    data['lore']=lore
    data['kaoju']={'verdict':kj.get('verdict'),'recommend':rec,'confidence':kj.get('confidence'),
        'sources':kj.get('sources'),'corrections':kj.get('corrections'),
        'verify_overall':vf.get('overall'),'verify_issues':vf.get('issues'),'reviewed':'2026-06-13'}
    clean = (rec=='upgrade' and vf.get('overall')=='confirmed')
    if clean:
        conf,defsrc='high','authored'; stats['authored']+=1
    else:
        conf,defsrc='low','derived'
        if rec=='delete': data['kaoju']['flag']='delete'; stats['flagged_delete']+=1
        elif rec=='merge': data['kaoju']['flag']='merge'; data['kaoju']['merge_into']=kj.get('merge_into'); stats['flagged_merge']+=1
        else: stats['enriched_low']+=1
    data['conf']=conf; data['def_src']=defsrc
    cur.execute("update style_nodes set data=%s, conf=%s, def_src=%s where style_id=%s",
                (json.dumps(data,ensure_ascii=False),conf,defsrc,_id))
conn.commit()
print("写回完成:",stats)
cur.execute("select conf,count(*) from style_nodes group by conf")
print("全库 conf 分布:",dict(cur.fetchall()))
conn.close()
# 回滚: TRUNCATE style_nodes; INSERT INTO style_nodes SELECT * FROM style_nodes_bak_20260613;
