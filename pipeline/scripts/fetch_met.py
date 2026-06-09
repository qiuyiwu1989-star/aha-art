#!/usr/bin/env python3
"""改用 Met 开放数据 + 本地托管图片(彻底解决外链被墙)。
抓约 120 件公共领域名画 → 下载图到 /data/pub/p/aha/img → 本地生成 thumb/lqip/主色/情绪 →
重建 data/artworks.json + data/graph.json(图片走本地 /aha/img/…)。"""
import json, urllib.request, urllib.parse, time, io, base64, colorsys, os, math, sys
from collections import defaultdict, deque
from PIL import Image

REPO = "/home/ubuntu/users/qiuyiwu/aha-art-demo"
IMGDIR = "/data/pub/p/aha/img"; TDIR = IMGDIR + "/t"
os.makedirs(TDIR, exist_ok=True)
UA = "aha-demo/1.0 (research; contact dev@zaowuyun.com)"
MET = "https://collectionapi.metmuseum.org/public/collection/v1"

def api(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

# 检索词(多样 + 可连接)
QUERIES = ["Monet","Van Gogh","Rembrandt","Vermeer","Turner","Cézanne","Renoir","Degas",
 "Pissarro","Gauguin","Sargent","Manet","Courbet","Corot","El Greco","Goya","Caravaggio",
 "Hokusai","Hiroshige","Chinese landscape painting","Japanese screen","impressionism",
 "landscape painting","portrait painting","still life flowers","seascape",
 # —— 扩充:更亮 / 更彩 / 更跨文化(铺开冷暖·明亮·东西方)——
 "Utamaro","ukiyo-e woodblock print","Persian miniature","Indian miniature painting",
 "Mughal painting","Ottoman illumination","tulip still life","fruit still life",
 "Hudson River School","American Impressionism","Tiffany stained glass","floral textile",
 "Japanese fan painting","Mary Cassatt","Berthe Morisot","Whistler","Constable","Bruegel"]
TARGET = 150

def get_ids(q):
    try:
        d = api(f"{MET}/search?q={urllib.parse.quote(q)}&hasImages=true")
        return d.get("objectIDs") or []
    except Exception: return []

print("收集 Met 公共领域作品…")
seen=set(); raw=[]
for q in QUERIES:
    if len(raw) >= TARGET: break
    ids = get_ids(q)[:18]
    for oid in ids:
        if len(raw) >= TARGET: break
        if oid in seen: continue
        seen.add(oid)
        try: o = api(f"{MET}/objects/{oid}")
        except Exception: continue
        if not o.get("isPublicDomain"): continue
        img = o.get("primaryImageSmall") or o.get("primaryImage")
        if not img: continue
        raw.append(o)
    print(f"  {q:<26} 累计 {len(raw)}")
    time.sleep(0.25)
print(f"共 {len(raw)} 件,开始下载图片…")

# ── 富集助手 ──
def warmth(h): return (math.cos(math.radians(h-40))+1)/2
def clamp(x): return max(0.0,min(1.0,x))
SUBJ=[("portrait","人物"),("women","人物"),("woman","人物"),("man","人物"),("men","人物"),("child","童真"),
 ("landscape","自然"),("tree","自然"),("garden","花卉"),("flower","花卉"),("mountain","自然"),
 ("water","海"),("sea","海"),("river","海"),("ship","海"),("boat","海"),
 ("still life","静物"),("fruit","静物"),("animal","动物"),("horse","动物"),("bird","动物"),
 ("religio","灵性"),("christ","灵性"),("saint","灵性"),("god","神话"),("myth","神话"),
 ("night","夜"),("city","都市"),("street","都市"),("dance","夜生活"),("music","夜生活"),("nude","人体")]
def themes_of(o, hsl):
    ts=[]
    pool=[(t.get("term","") if isinstance(t,dict) else str(t)).lower() for t in (o.get("tags") or [])]
    pool.append((o.get("classification") or "").lower()); pool.append((o.get("title") or "").lower())
    pool.append((o.get("objectName") or "").lower())
    for s in pool:
        for k,v in SUBJ:
            if k in s and v not in ts: ts.append(v)
    h,sa,l=hsl
    if l>0.6: ts.append("明亮")
    elif l<0.32: ts.append("幽暗")
    if warmth(h)>0.6 and sa>0.25: ts.append("暖")
    elif warmth(h)<0.35 and sa>0.2: ts.append("冷")
    if not ts: ts.append(o.get("classification") or "作品")
    out=[]; [out.append(t) for t in ts if t not in out]
    return out[:5]
def century(y):
    if not y: return None
    return (y//100+1) if y>0 else (y//100-1)

works=[]
for o in raw:
    oid=o["objectID"]; slug="m"+str(oid)
    url=o.get("primaryImageSmall") or o.get("primaryImage")
    local=f"{IMGDIR}/{slug}.jpg"
    try:
        if os.path.exists(local):                       # 已下过 → 直接用本地图(省网络,可重跑)
            im=Image.open(local).convert("RGB"); w,h=im.size
        else:
            req=urllib.request.Request(url, headers={"User-Agent":UA})
            data=urllib.request.urlopen(req, timeout=45).read()
            im=Image.open(io.BytesIO(data)).convert("RGB")
            w,h=im.size; scale=min(1.0,1100/max(w,1))
            web=im.resize((max(1,int(w*scale)),max(1,int(h*scale)))) if scale<1 else im
            web.save(local,"JPEG",quality=82)
            s2=min(1.0,320/max(w,1)); th=im.resize((max(1,int(w*s2)),max(1,int(h*s2)))) if s2<1 else im
            th.save(f"{TDIR}/{slug}.jpg","JPEG",quality=80)
    except Exception as e:
        print("  skip(dl/decode)",slug,repr(e)[:60],file=sys.stderr); continue
    # lqip(12宽)+ 主色
    tiny=im.resize((12,max(1,int(12*h/w))))
    buf=io.BytesIO(); tiny.save(buf,"JPEG",quality=40)
    lqip="data:image/jpeg;base64,"+base64.b64encode(buf.getvalue()).decode()
    px=im.resize((1,1)).getpixel((0,0)); r,g,b=px[0],px[1],px[2]
    hh,ll,ss=colorsys.rgb_to_hls(r/255,g/255,b/255); H=hh*360
    hsl=(H,ss,ll)
    val=round(clamp(0.28+0.5*ll+0.22*warmth(H)),2)
    aro=round(clamp(0.2+0.55*ss+0.2),2) if False else round(clamp(0.25+0.55*ss),2)
    y0=o.get("objectBeginDate")
    title=o.get("title") or "Untitled"; artist=o.get("artistDisplayName") or o.get("culture") or "佚名"
    works.append({
        "slug":slug,"title":title,"artist":artist,"date":o.get("objectDate"),
        "year":y0,"century":century(y0),"medium":o.get("medium"),"origin":o.get("culture") or o.get("country"),
        "style":(o.get("period") or o.get("culture") or None),"themes":themes_of(o,hsl),
        "image":f"/aha/img/{slug}.jpg","thumb":f"/aha/img/t/{slug}.jpg","lqip":lqip,"alt":title,
        "color":{"rgb":[r,g,b],"hsl":[round(H),round(ss,2),round(ll,2)]},
        "mood":{"valence":val,"arousal":aro},
        "oneLiner":f"{artist}{('·'+o['objectDate']) if o.get('objectDate') else ''}。{(o.get('classification') or '')}",
        "look":f"留意它的色调与构图。",
    })
    print("  ✓",slug,artist[:14],title[:24])

print(f"\n成功 {len(works)} 件。建图…")
BY={w["slug"]:w for w in works}; slugs=set(BY)
adj=defaultdict(set); edges=[]; seen_e=set(); CAP=7
def cdist(a,b):
    dh=abs(a[0]-b[0]); dh=min(dh,360-dh)/180
    return dh*1.4+abs(a[1]-b[1])+abs(a[2]-b[2])*0.8
def add(a,bb,t,why):
    if a==bb: return
    k=tuple(sorted((a,bb)))
    if k in seen_e: return
    if len(adj[a])>=CAP or len(adj[bb])>=CAP: return
    seen_e.add(k); adj[a].add(bb); adj[bb].add(a); edges.append({"a":a,"b":bb,"type":t,"why":why})
# 同艺术家链
ba=defaultdict(list)
for w in works:
    if w["artist"] and w["artist"]!="佚名": ba[w["artist"]].append(w)
for art,ws in ba.items():
    ws.sort(key=lambda x:x.get("year") or 0)
    for i in range(len(ws)-1): add(ws[i]["slug"],ws[i+1]["slug"],"artist",f"同是{art}的作品。")
# 同母题(各 2)
for w in works:
    c=[]
    for o in works:
        if o is w: continue
        sh=set(w["themes"])&set(o["themes"])
        if sh: c.append((len(sh),-abs((o.get("year") or 0)-(w.get("year") or 0)),o,next(iter(sh))))
    c.sort(key=lambda x:(-x[0],x[1]))
    for _,_,o,sh in c[:2]: add(w["slug"],o["slug"],"theme",f"同母题:{sh}。")
# 色彩呼应(各 2)
for w in works:
    wc=w["color"]["hsl"]
    cs=sorted([o for o in works if o is not w],key=lambda o:cdist(wc,o["color"]["hsl"]))
    for o in cs[:2]: add(w["slug"],o["slug"],"formal","色彩气质相近。")
# 救援孤立点
for w in works:
    if len(adj[w["slug"]])==0:
        wc=w["color"]["hsl"]; o=min((x for x in works if x is not w),key=lambda x:cdist(wc,x["color"]["hsl"]))
        k=tuple(sorted((w["slug"],o["slug"])))
        if k not in seen_e: seen_e.add(k);adj[w["slug"]].add(o["slug"]);adj[o["slug"]].add(w["slug"]);edges.append({"a":w["slug"],"b":o["slug"],"type":"formal","why":"色彩气质相近。"})

graph={"typeLabels":{"influence":"影响","theme":"同母题","formal":"形式呼应","artist":"同艺术家","movement":"同流派"},"edges":edges}
json.dump(works,open(f"{REPO}/data/artworks.json","w"),ensure_ascii=False,indent=1)
json.dump(graph,open(f"{REPO}/data/graph.json","w"),ensure_ascii=False,indent=1)
# 连通自检
st=next(iter(slugs)); vis={st}; q=deque([st])
while q:
    for n in adj[q.popleft()]:
        if n not in vis: vis.add(n); q.append(n)
print(f"作品 {len(works)} · 边 {len(edges)} · 连通 {len(vis)}/{len(slugs)} · 本地图 {len(os.listdir(IMGDIR))-1} 张")
