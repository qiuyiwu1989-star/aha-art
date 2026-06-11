#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""桥表:202 风格库 → (西方32标准码 canonical) + (东方子谱系 eastern_lineage)。
草表,inferred 项需人工审。输出 /data/pub/p/aha/data/kg_style_canonical.json"""
import json, re, sys
sys.path.insert(0,'.')
from style_norm import to_style_id, CANON

N=json.load(open('/data/pub/p/aha/data/kg_style.json'))['nodes']
zh32={c[0]:c[1] for c in CANON}

# ---- 东方子谱系:12 类 + 有序关键词规则(先具体后宽泛) ----
EAST_CANON=[
 ("e_prehistoric_object","史前与器物纹饰","岩画/彩陶/青铜纹饰/画像石砖"),
 ("e_tomb_silk","墓葬与帛画","帛画/墓室壁画/画像"),
 ("e_religious","宗教绘画","佛教/道教/造像/敦煌/永乐宫/唐卡/藏传"),
 ("e_landscape","山水画","青绿/水墨/写意/院体山水/金碧"),
 ("e_literati_ink","文人水墨","文人画/墨竹梅/四僧八大/禅意"),
 ("e_bird_flower","花鸟画","工笔/写意花鸟/没骨"),
 ("e_figure","人物画","仕女/白描/工笔写意人物"),
 ("e_regional_school","地域画派","浙吴松江海派岭南金陵新安常州金石"),
 ("e_gongbi_color","工笔与重彩","工笔/重彩/岩彩/界画"),
 ("e_japan","日本绘画","琳派/狩野派/大和绘/南画(浮世绘归西32)"),
 ("e_korea","朝鲜绘画","朝鲜民画"),
 ("e_contemporary_ink","现当代水墨","实验/观念/数字/新中国画/政治题材/民间转型"),
 ("e_folk","民间美术","年画/剪纸/漆画/少数民族/地方民俗"),
]
EZH={c[0]:c[1] for c in EAST_CANON}
# 有序规则:命中即停
ERULES=[
 (r"岩画|彩陶|青铜|画像石|画像砖|宗庙", "e_prehistoric_object"),
 (r"帛画|墓室|墓葬", "e_tomb_silk"),
 (r"佛教|佛像|造像|道教|敦煌|永乐宫|唐卡|藏传|宗教", "e_religious"),
 (r"年画|剪纸|漆画|少数民族|地方民俗|民俗", "e_folk"),
 (r"琳派|狩野|大和绘|日本南画|南画", "e_japan"),
 (r"朝鲜", "e_korea"),
 (r"实验水墨|观念水墨|数字与ai|数字与AI|新媒体|行为与影像|社会与生态|科技山水|虚空绘画|多媒介水墨|综合材料|装置与空间|观念绘画|新中国画|政治题材|宣传画|革新文人画|表现水墨|书写性水墨|情绪笔墨|自然笔墨", "e_contemporary_ink"),
 (r"没骨|界画", "e_gongbi_color"),
 (r"浙派|吴派|松江|海派|岭南|金陵|新安|常州|金石|南宗|北宗", "e_regional_school"),
 (r"花鸟", "e_bird_flower"),
 (r"仕女|白描|人物", "e_figure"),
 (r"山水|青绿|金碧|院体|小景|李思训", "e_landscape"),
 (r"工笔|重彩|岩彩|淡彩", "e_gongbi_color"),
 (r"文人|墨竹|墨梅|四僧|八大|禅|写意|留白|寫形|寫神|笔墨|水墨", "e_literati_ink"),
]
ECOMP=[(re.compile(p,re.I),c) for p,c in ERULES]
def east_lineage(name):
    for rx,c in ECOMP:
        if rx.search(name): return c
    return None

out=[]; stats={'west_mapped':0,'west_other':0,'east_mapped':0,'east_inferred':0,'east_unmatched':0}
for x in N:
    cn=x['cn']; cands=[cn]+(x.get('aka') or [])
    sid='other'
    for c in cands:
        s=to_style_id(c)
        if s and s!='other': sid=s; break
    rec={'id':x['id'],'cn':cn,'region':x.get('region'),'wv':x.get('wv'),
         'canonical':sid, 'eastern_lineage':None, 'bridge_conf':'rule' if sid!='other' else None}
    if x.get('region')=='west':
        stats['west_mapped' if sid!='other' else 'west_other']+=1
    else: # east
        if sid!='other':
            stats['east_mapped']+=1   # 浮世绘/东方主义等已在32
        else:
            el=east_lineage(cn)
            rec['eastern_lineage']=el
            rec['bridge_conf']='inferred'
            if el: stats['east_inferred']+=1
            else: stats['east_unmatched']+=1
    out.append(rec)

doc={'note':'202风格库→标准码桥表。canonical=西方32码;eastern_lineage=东方12子谱系(inferred,需人工审)。生成于2026-06-11',
     'west_canon':[{'id':c[0],'zh':c[1]} for c in CANON],
     'east_canon':[{'id':c[0],'zh':c[1],'scope':c[2]} for c in EAST_CANON],
     'map':out}
json.dump(doc,open('/data/pub/p/aha/data/kg_style_canonical.json','w'),ensure_ascii=False,indent=1)

print("桥表已写 → data/kg_style_canonical.json")
print("覆盖统计:",json.dumps(stats,ensure_ascii=False))
um=[r['cn'] for r in out if r['region']=='east' and r['canonical']=='other' and not r['eastern_lineage']]
print(f"\n东方仍未匹配(需手动) {len(um)}:", um)
# 西方掉 other 的明细
wo=[r['cn'] for r in out if r['region']=='west' and r['canonical']=='other']
print(f"\n西方掉 other {len(wo)}:", wo)
