#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DB → JSON 导出:style_nodes 是真相源,本脚本吐 kg_style.json 给页面读(build 缓存)。
meta/models/xis 仍取自现有 JSON(稳定配置);nodes 全部从库重建,并带上 canonical/eastern_lineage。
用法: python3 export_style_nodes.py            # 写 /data/pub/p/aha/data/kg_style.json
      python3 export_style_nodes.py --dry      # 只比对,不写"""
import json, os, sys, psycopg2
OUT='/data/pub/p/aha/data/kg_style.json'
d=json.load(open(os.path.expanduser("~/.aha_pg.json")))
cn=psycopg2.connect(host=d["host"],port=d["port"],dbname=d["dbname"],user=d["user"],password=d["password"])
cur=cn.cursor()
cur.execute("SELECT data, canonical, eastern_lineage, bridge_conf FROM style_nodes ORDER BY sort")
nodes=[]
for data,canon,el,bc in cur.fetchall():
    n=dict(data)                       # 原节点零丢失
    n['canonical']=canon               # 桥:32 标准码(供页面接作品)
    if el: n['eastern_lineage']=el
    if bc: n['bridge_conf']=bc
    nodes.append(n)
cn.close()

cur_doc=json.load(open(OUT))           # 复用稳定的 meta/models/xis
doc={'meta':cur_doc.get('meta',{}),'models':cur_doc.get('models',[]),
     'xis':cur_doc.get('xis',[]),'nodes':nodes}
doc['meta']['source_of_truth']='postgres:style_nodes'
doc['meta']['built_by']='export_style_nodes.py'

if '--dry' in sys.argv:
    print(f"[dry] 库出 {len(nodes)} 节点;现 JSON {len(cur_doc['nodes'])} 节点")
    print("  带 canonical 的:", sum(1 for n in nodes if n.get('canonical')))
else:
    json.dump(doc,open(OUT,'w'),ensure_ascii=False,indent=1)
    print(f"✓ 写出 {len(nodes)} 节点 → {OUT}(库为真相源)")
    print("  带 canonical:", sum(1 for n in nodes if n.get('canonical')),
          " 带 eastern_lineage:", sum(1 for n in nodes if n.get('eastern_lineage')))
