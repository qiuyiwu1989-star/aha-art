#!/usr/bin/env python3
"""把语料过滤成只留绘画/版画/素描(去掉瓷器/器物/雕塑),并重建图谱。复用已下载的本地图。"""
import json, math, colorsys
from collections import defaultdict, deque
REPO="/home/ubuntu/users/qiuyiwu/aha-art-demo"
works=json.load(open(f"{REPO}/data/artworks.json"))

KEEP=("oil","canvas","tempera","panel","watercolor","gouache","ink","paper","print","etching",
 "woodblock","woodcut","lithograph","engraving","drawing","chalk","pastel","fresco","silk","scroll","album")
DROP_TITLE=("vase","cup","pot","jar","ewer","teapot","bottle","coupe","cage","bowl","plate","dish",
 "censer","figure of","statue","sculpture","screen","box","covered","wine pot","porcelain")
def keep(w):
    m=(w.get("medium") or "").lower(); t=(w.get("title") or "").lower()
    if any(k in t for k in DROP_TITLE): return False
    if any(k in m for k in KEEP): return True
    # medium 不明时,靠 classification(存在 oneLiner 尾部)兜底:含 painting/print/drawing
    o=(w.get("oneLiner") or "").lower()
    return any(k in o for k in ("painting","print","drawing"))

kept=[w for w in works if keep(w)]
print(f"原 {len(works)} → 留 {len(kept)} 件绘画/版画/素描")

BY={w["slug"]:w for w in kept}; slugs=set(BY)
adj=defaultdict(set); edges=[]; seen_e=set(); CAP=7
def cdist(a,b):
    dh=abs(a[0]-b[0]); dh=min(dh,360-dh)/180
    return dh*1.4+abs(a[1]-b[1])+abs(a[2]-b[2])*0.8
def add(a,bb,t,why):
    if a==bb: return
    k=tuple(sorted((a,bb)))
    if k in seen_e or len(adj[a])>=CAP or len(adj[bb])>=CAP: return
    seen_e.add(k);adj[a].add(bb);adj[bb].add(a);edges.append({"a":a,"b":bb,"type":t,"why":why})
ba=defaultdict(list)
for w in kept:
    if w["artist"] and w["artist"]!="佚名": ba[w["artist"]].append(w)
for art,ws in ba.items():
    ws.sort(key=lambda x:x.get("year") or 0)
    for i in range(len(ws)-1): add(ws[i]["slug"],ws[i+1]["slug"],"artist",f"同是{art}的作品。")
for w in kept:
    c=[]
    for o in kept:
        if o is w: continue
        sh=set(w["themes"])&set(o["themes"])
        if sh: c.append((len(sh),-abs((o.get("year") or 0)-(w.get("year") or 0)),o,next(iter(sh))))
    c.sort(key=lambda x:(-x[0],x[1]))
    for _,_,o,sh in c[:2]: add(w["slug"],o["slug"],"theme",f"同母题:{sh}。")
for w in kept:
    wc=w["color"]["hsl"]
    cs=sorted([o for o in kept if o is not w],key=lambda o:cdist(wc,o["color"]["hsl"]))
    for o in cs[:2]: add(w["slug"],o["slug"],"formal","色彩气质相近。")
for w in kept:
    if not adj[w["slug"]]:
        wc=w["color"]["hsl"]; o=min((x for x in kept if x is not w),key=lambda x:cdist(wc,x["color"]["hsl"]))
        k=tuple(sorted((w["slug"],o["slug"])))
        if k not in seen_e: seen_e.add(k);adj[w["slug"]].add(o["slug"]);adj[o["slug"]].add(w["slug"]);edges.append({"a":w["slug"],"b":o["slug"],"type":"formal","why":"色彩气质相近。"})

graph={"typeLabels":{"influence":"影响","theme":"同母题","formal":"形式呼应","artist":"同艺术家","movement":"同流派"},"edges":edges}
json.dump(kept,open(f"{REPO}/data/artworks.json","w"),ensure_ascii=False,indent=1)
json.dump(graph,open(f"{REPO}/data/graph.json","w"),ensure_ascii=False,indent=1)
st=next(iter(slugs)); vis={st}; q=deque([st])
while q:
    for n in adj[q.popleft()]:
        if n not in vis: vis.add(n);q.append(n)
print(f"留 {len(kept)} · 边 {len(edges)} · 连通 {len(vis)}/{len(slugs)}")
