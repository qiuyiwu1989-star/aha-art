#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作品索引 v2:by_node(富节点精确细分,白嫖 style.流派)+ by_canonical(兜底组粒度)。
策展作品的 style.流派 串能落到具体富节点的→精确;否则归到 canonical 组。零 VLM。"""
import json, re
from collections import defaultdict

NODES=[n for n in json.load(open('/data/pub/p/aha/data/kg_style.json'))['nodes']]
ART=json.load(open('/data/pub/p/aha/data/live/artworks_v2.json'))['artworks']

# 富节点 → 匹配模式(cn 去后缀 + aka + 少量同义)。同 canonical 组内匹配,避免跨组误伤。
SYN={  # 流派串里的说法 → 该富节点 cn 的别名
 '高文艺复兴':['盛期','文艺复兴盛期','rococo盛期'],'早期文艺复兴':['文艺复兴早期','早期文艺复兴','quattrocento'],
 '晚期文艺复兴':['样式主义','矫饰','late renaissance'],'北方文艺复兴':['尼德兰','弗拉芒','flemish','北方'],
 '社会现实主义':['社会现实','社会主义现实'],'照相写实主义':['照相写实','photoreal'],'超写实主义':['超写实','hyperreal'],
 '魔幻现实主义':['魔幻现实','幻想现实'],'点彩派':['点彩','新印象','分隔'],'分析立体主义':['分析立体'],
 '综合立体主义':['综合立体'],'色域绘画':['色域'],'动作绘画':['动作','行动绘画'],
}
def keys(n):
    cn=n['cn']; base=re.sub(r'(风格|画风|主义)$','',cn)
    ks=set([cn,base]+ (n.get('aka') or []) + SYN.get(cn,[]))
    return {k.lower() for k in ks if k and len(k)>=2}

# 按 canonical 分组富节点
bycanon=defaultdict(list)
for n in NODES:
    if n.get('canonical'): bycanon[n['canonical']].append(n)

def match_node(canon, liupai):
    """在 canon 组里找 cn/别名命中 流派串 的富节点;命中多个取最长 key。"""
    if not liupai: return None
    s=liupai.lower(); best=None; bl=-1
    for n in bycanon.get(canon,[]):
        for k in keys(n):
            if k in s and len(k)>bl: best=n['id']; bl=len(k)
    return best

by_node=defaultdict(list); by_canon=defaultdict(list); fine=0; group=0
for v in ART.values():
    if not v.get('thumb'): continue
    c=v.get('style_id')
    if not c: continue
    st=v.get('style'); liu = st.get('流派') if isinstance(st,dict) else (st if isinstance(st,str) else '')
    item={'slug':v.get('slug'),'title':v.get('title'),'artist':v.get('artist'),'thumb':v.get('thumb'),'full':v.get('full')}
    by_canon[c].append(item)
    nid=match_node(c, liu or '')
    if nid: by_node[nid].append(item); fine+=1
    else: group+=1

zh={c[0]:c[1] for c in __import__('style_norm').CANON}
out={'meta':{'note':'by_node=富节点精确(白嫖style.流派);by_canonical=组兜底;canon_zh=标准码中文','built_by':'_build_style_works2.py'},
     'canon_zh':zh,
     'count':{k:len(v) for k,v in by_canon.items()},
     'count_node':{k:len(v) for k,v in by_node.items()},
     'by_node':{k:v[:18] for k,v in by_node.items()},
     'by_canonical':{k:v[:18] for k,v in by_canon.items()}}
json.dump(out,open('/data/pub/p/aha/data/kg_style_works.json','w'),ensure_ascii=False,indent=0)
print(f"精确落到富节点:{fine} 件;兜底到组:{group} 件")
print(f"有精确作品的富节点:{len(by_node)} 个")
# 抽样
for nid in list(by_node):
    n=next(x for x in NODES if x['id']==nid)
    if n['cn'] in('北方文艺复兴','早期文艺复兴','高文艺复兴','威尼斯画派','超写实主义','点彩派'):
        print(f"   {nid} {n['cn']}: {len(by_node[nid])} 件")
