# -*- coding: utf-8 -*-
# 分析 VLM 情绪取证:与像素/独立人工VAD/语料mood 对照,看多通道是否胜过纯像素。
import json, math
from collections import Counter, defaultdict
def L(f): return json.load(open(f,encoding='utf-8'))
M=L('kg_affect_measured.json'); rows=M['rows']           # 57 已映射(含 feat/art_a/art_v/mood_a/style坐标)
byslug={r['slug']:r for r in rows}
VLM={}
for line in open('kg_affect_vlm.jsonl',encoding='utf-8'):
    try:
        r=json.loads(line)
        if r.get('vlm') and isinstance(r['vlm'].get('vad'),dict): VLM[r['slug']]=r['vlm']
    except Exception: pass
n_all=len(VLM)
print('VLM 成功解析:',n_all,'幅')

def pearson(xs,ys):
    pts=[(x,y) for x,y in zip(xs,ys) if x is not None and y is not None]
    n=len(pts)
    if n<5: return None,n
    mx=sum(p[0] for p in pts)/n; my=sum(p[1] for p in pts)/n
    sxy=sum((a-mx)*(b-my) for a,b in pts); sxx=sum((a-mx)**2 for a,_ in pts); syy=sum((b-my)**2 for _,b in pts)
    if sxx==0 or syy==0: return None,n
    return sxy/math.sqrt(sxx*syy),n

# 锚点分布 / 置信 / VAD 概览
anchors=Counter(v.get('primary_anchor') for v in VLM.values())
conf=[v.get('confidence') for v in VLM.values() if isinstance(v.get('confidence'),(int,float))]
print('\\n锚点分布:',dict(anchors.most_common()))
print('平均置信:',round(sum(conf)/len(conf),2) if conf else '-')

# 关键对照:把 VLM 的 VAD 接到 measured 行(按 slug)
def col(key):  # 取交集向量
    xs=[];ys=[]
    for slug,v in VLM.items():
        r=byslug.get(slug)
        if not r: continue
        a=v['vad'].get(key[0]); b=r.get(key[1]) if key[1] in r else (r['feat'].get(key[1]) if key[1] in r['feat'] else None)
        xs.append(a); ys.append(b)
    return xs,ys

tests=[
 ("VLM唤起","arousal","art_a","独立人工考据·唤起 ★关键"),
 ("VLM唤起","arousal","sat","像素·饱和度"),
 ("VLM唤起","arousal","mood_a","语料mood唤起(颜色派生)"),
 ("VLM愉悦","valence","art_v","独立人工考据·愉悦 ★关键"),
 ("VLM愉悦","valence","val","像素·明度"),
 ("VLM愉悦","valence","mood_v","语料mood愉悦"),
 ("VLM支配","dominance","ord_ten","E向量·秩序张力"),
]
print('\\n=== VLM-VAD 对照(r,n)===')
out_corr={}
for lab,vk,rk,desc in tests:
    xs=[];ys=[]
    for slug,v in VLM.items():
        r=byslug.get(slug)
        if not r: continue
        a=v['vad'].get(vk)
        b=r.get(rk);
        if b is None and rk in r.get('feat',{}): b=r['feat'][rk]
        xs.append(a); ys.append(b)
    rr,nn=pearson(xs,ys)
    out_corr[lab+'~'+rk]={"r":round(rr,3) if rr is not None else None,"n":nn,"desc":desc}
    print(f"  {lab} ~ {desc.ljust(22)} r={rr if rr is None else round(rr,3)} (n{nn})")

# 对比基线:纯像素饱和 ~ 独立人工唤起(上轮的 0.20)
base_r,base_n=pearson([byslug[s]['feat']['sat'] for s in byslug],[byslug[s].get('art_a') for s in byslug])
print(f"\\n[基线] 纯像素饱和 ~ 独立人工唤起: r={round(base_r,3)} (n{base_n})")
vlm_key=[v for v in out_corr if v.startswith('VLM唤起~art_a')]
if vlm_key:
    print(f"[对比] VLM唤起 ~ 独立人工唤起: r={out_corr[vlm_key[0]]['r']} (n{out_corr[vlm_key[0]]['n']})")

# 通道引用:三通道里哪个最常被作为依据(粗略:看 evidence/通道文本里关键词)
ch_used=Counter()
for v in VLM.values():
    for ch,kw in [("构图姿态","ch_composition"),("题材语义","ch_subject"),("光色","ch_lightcolor")]:
        t=v.get(kw,'')
        if t and len(t)>4: ch_used[ch]+=1
print('\\n三通道被填写次数:',dict(ch_used))

summary={"n_vlm":n_all,"anchors":dict(anchors.most_common()),"mean_conf":round(sum(conf)/len(conf),2) if conf else None,
         "corr":out_corr,"baseline_pixel_arousal_vs_curated":{"r":round(base_r,3) if base_r else None,"n":base_n}}
json.dump(summary,open('kg_affect_vlm_summary.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('\\n已写 kg_affect_vlm_summary.json')
