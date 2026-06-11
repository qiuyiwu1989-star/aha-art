#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 _build_bridge 基础上补:西方中文名补充规则(填 style_norm 漏掉的)+ 6 个东方手动归位。
重新生成 kg_style_canonical.json,并导出 style_norm 需补的中文别名清单。"""
import json, re, sys
sys.path.insert(0,'.')
from style_norm import to_style_id, CANON
N=json.load(open('/data/pub/p/aha/data/kg_style.json'))['nodes']

# 西方:中文名补充规则(style_norm 因只认英文而漏)。命中即停。
WEST_SUP=[
 (r"古希腊|古罗马", "classicism"),          # 填空壳:古典主义
 (r"罗马式", "medieval"),
 (r"佛罗伦萨|威尼斯画派|锡耶纳", "renaissance"),
 (r"荷兰黄金", "baroque"),
 (r"纳比派", "post_impressionism"),
 (r"蓝骑士|桥社|新即物", "expressionism"),
 (r"形而上", "surrealism"),
 (r"动作绘画|色域", "abstract_expressionism"),
 (r"至上主义|构成主义|新造型|非形式|硬边|欧普|光效应|极简", "abstract_art"),
 (r"照相写实|超写实|巴比松", "realism"),
 (r"素人绘画", "naive_art"),                  # 填空壳:素朴艺术
 (r"观念艺术|算法与生成|数字绘画|沉浸与环境|网络与后互联网|区块链|NFT|街头|涂鸦|大地艺术|贫穷艺术", "contemporary"),
]
WCOMP=[(re.compile(p,re.I),c) for p,c in WEST_SUP]
def west_sup(name):
    for rx,c in WCOMP:
        if rx.search(name): return c
    return None

# 6 个东方手动
EAST_MANUAL={
 '壁画风格':'e_religious','唐代宫廷绘画':'e_figure','牧溪风格':'e_literati_ink',
 '扬州八怪风格':'e_regional_school','宫廷画风':'e_figure','写实主义风格':'e_contemporary_ink',
}

doc=json.load(open('/data/pub/p/aha/data/kg_style_canonical.json'))
sup_aliases=[]   # 给 style_norm 补的中文别名:(cn, canonical)
for r in doc['map']:
    if r['region']=='west' and r['canonical']=='other':
        c=west_sup(r['cn'])
        if c:
            r['canonical']=c; r['bridge_conf']='rule_zh_supplement'
            sup_aliases.append((r['cn'],c))
    if r['region']=='east' and not r.get('eastern_lineage') and r['canonical']=='other':
        if r['cn'] in EAST_MANUAL:
            r['eastern_lineage']=EAST_MANUAL[r['cn']]; r['bridge_conf']='manual'

json.dump(doc,open('/data/pub/p/aha/data/kg_style_canonical.json','w'),ensure_ascii=False,indent=1)

# 复核
from collections import Counter
west=[r for r in doc['map'] if r['region']=='west']
east=[r for r in doc['map'] if r['region']=='east']
print("西方 other 残留:", [r['cn'] for r in west if r['canonical']=='other'])
print("东方 仍无谱系:", [r['cn'] for r in east if not r.get('eastern_lineage') and r['canonical']=='other'])
print("\n东方子谱系分布:", dict(Counter(r['eastern_lineage'] for r in east if r['eastern_lineage'])))
# 导出 style_norm 待补别名
json.dump(sup_aliases, open('_style_norm_missing_zh_aliases.json','w'), ensure_ascii=False, indent=1)
print(f"\n→ style_norm.py 该补的中文别名 {len(sup_aliases)} 条,已存 _style_norm_missing_zh_aliases.json")
