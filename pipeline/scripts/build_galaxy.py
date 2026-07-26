#!/usr/bin/env python3
# 生成 data/kg_galaxy.json —— 星辰大海 demo 的真实数据底座
# 关联度只用「真实美术史关系」: 风格志手写的 承自/影响/对抗 + 隶属(→世界模型)
# 不使用作品共现(部分作品非真实)。预算 4 套布局坐标供前端切换。
import json, math, random, re, os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 数据底座=全站读的那份(aha-art-demo/data,含 WV 修正/新增/谱系最新);可用 AHA_DATA 覆盖
DATA = os.environ.get('AHA_DATA', '/home/ubuntu/users/qiuyiwu/aha-art-demo/data')
SRC  = os.path.join(DATA, 'kg_style.json')
ART  = os.path.join(DATA, 'kg_artists.json')
OUT  = os.path.join(DATA, 'kg_galaxy.json')
random.seed(42)

d = json.load(open(SRC, encoding='utf-8'))
nodes = [n for n in d['nodes'] if n.get('coord')]
models_meta = {m['code']: m for m in d.get('models', [])}
byId = {n['id']: n for n in nodes}

# ---------- 名称 → id 解析(把 lore 关系名连到真实节点;含傘流派展开) ----------
# 背景: V3 整理把傘流派拆成地域变种(巴洛克→意/西/法…),故"承自巴洛克"应连到其全部变种。
SUF=['风格','主义','画派','画风','派']
def strip_suf(s):
    for suf in SUF:
        if s.endswith(suf) and len(s)>len(suf)+1: return s[:-len(suf)]
    return s
exact={}; alias={}
for n in nodes:
    i=n['id']
    for key in (n['cn'], strip_suf(n['cn'])): exact.setdefault(key,i)
    if n.get('cn_alt'):
        alias.setdefault(n['cn_alt'],i); alias.setdefault(strip_suf(n['cn_alt']),i)
    for a in (n.get('lore',{}).get('aka') or []): alias.setdefault(a,i); alias.setdefault(strip_suf(a),i)
cn_list=[(n['cn'],n['id']) for n in nodes]
confrank={'high':0,'med':1,'low':2}
def crank(i): return confrank.get(byId[i].get('conf'),3)

# 精选人工映射: 拆分/改名后无法自动命中、但有公认对应的真实关系
CURATED={
    '宋代山水':['STYLE.east.029','STYLE.east.030'],   # 北宋山水 + 南宋山水
    '院体画':['STYLE.east.026','STYLE.east.083'],      # 北宋院体 + 乾隆院体
    '行动绘画':['STYLE.west.057'],                     # 行动画法 = 抽象表现主义一派
}
CURATED={k:[i for i in v if i in byId] for k,v in CURATED.items()}
def resolve_ids(nm):
    """返回 (ids[], method)。method: exact/alias/curated/suffix/umbrella/broader/unresolved"""
    if not nm: return [],'unresolved'
    nm=nm.strip()
    if nm in exact: return [exact[nm]],'exact'
    if nm in CURATED: return CURATED[nm],'curated'
    if nm in alias: return [alias[nm]],'alias'
    s=strip_suf(nm)
    if s in exact: return [exact[s]],'suffix'
    if s in alias: return [alias[s]],'alias'
    # 傘流派 → 变种: nm 是这些节点名的"词头/成分"
    variants=[]
    for cn,i in cn_list:
        if cn==nm: continue
        if nm in cn or (len(s)>=2 and s in cn): variants.append(i)
    variants=list(dict.fromkeys(variants))
    if variants:
        if len(variants)<=4: return variants,'umbrella'        # 大运动(≤4变种)连全部
        best=sorted(variants,key=lambda i:(crank(i),i))[0]      # 大家族(写意/工笔)连代表
        return [best],'umbrella'
    # 特定子类 → 上位: 某节点名包含于 nm
    broader=[(cn,i) for cn,i in cn_list if len(strip_suf(cn))>=2 and (cn in nm or strip_suf(cn) in nm)]
    if broader:
        broader.sort(key=lambda x:-len(x[0]))
        return [broader[0][1]],'broader'
    return [],'unresolved'

# ---------- 真实谱系边 ----------
def core(cn): return strip_suf(cn)
def edge_why(s,t):
    """从两端真实文本里找一句确证理由(某端 born/def 明确提到对方);返回 (理由, 出处)。找不到返回('','')诚实留空。
       出处 = 该句出自哪个流派的哪个字段(供信息卡显示可追溯脚注)。"""
    A,B=byId[s],byId[t]; aL=A.get('lore',{}); bL=B.get('lore',{})
    cand=[ (bL.get('born'),core(A['cn']),B['cn'],'born'), (B.get('def'),core(A['cn']),B['cn'],'def'),
           (aL.get('born'),core(B['cn']),A['cn'],'born'), (A.get('def'),core(B['cn']),A['cn'],'def') ]
    FLD={'born':'源起','def':'定义'}
    for text,name,owner,fld in cand:
        if text and name and len(name)>=2 and name in text:
            t2=text.strip()
            return (t2 if len(t2)<=110 else t2[:108]+'…', '风格志·'+owner+'·'+FLD[fld])
    return ('','')
edges=[]; seen=set(); method_ct={}; unresolved_names=set()
def add_edge(s,t,k,conf):
    if not s or not t or s==t: return
    key=(s,t,k)
    if key in seen: return
    why,src=edge_why(s,t)
    seen.add(key); edges.append({'s':s,'t':t,'k':k,'c':conf,'w':why,'src':src})
def link(refs, owner, kind, direction):
    for nm in refs:
        ids,m=resolve_ids(nm)
        method_ct[m]=method_ct.get(m,0)+1
        if m=='unresolved': unresolved_names.add(nm); continue
        conf='high' if m in ('exact','alias','suffix') else 'med'
        for tid in ids:
            if direction=='in':  add_edge(tid, owner, kind, conf)   # 父 → 本
            else:                add_edge(owner, tid, kind, conf)   # 本 → 对象
for n in nodes:
    lo=n.get('lore',{})
    link(lo.get('parents') or [], n['id'], 'parent', 'in')
    link(lo.get('influences') or [], n['id'], 'influence', 'out')
    ag=lo.get('against') or []
    if isinstance(ag,str): ag=[ag]
    link(ag, n['id'], 'against', 'out')
print('解析方法分布:', method_ct)
print('仍未解析(真无对应节点,已诚实丢弃):', len(unresolved_names), sorted(unresolved_names))

# 度数(用于星的亮度/大小)
deg={n['id']:0 for n in nodes}
for e in edges:
    deg[e['s']]=deg.get(e['s'],0)+1; deg[e['t']]=deg.get(e['t'],0)+1

# ---------- 年代解析(用于时间螺旋) ----------
def parse_year(txt):
    if not txt: return None
    bce = ('公元前' in txt) or txt.strip().startswith('前')
    # 年代 (1870年代)
    m=re.findall(r'(\d{3,4})\s*年代', txt)
    if m:
        ys=[int(x)+5 for x in m]; return sum(ys)/len(ys)
    # 世纪
    cents=re.findall(r'(\d{1,2})\s*[–\-~至]?\s*(?:前)?(\d{1,2})?\s*世纪', txt)
    nums=re.findall(r'(\d{1,2})\s*世纪', txt)
    if nums:
        vals=[int(x) for x in nums]
        lo, hi = min(vals), max(vals)
        y_lo = (lo-1)*100+50; y_hi=(hi-1)*100+50
        y=(y_lo+y_hi)/2
        return -y if bce else y
    # 明确年份
    yrs=[int(x) for x in re.findall(r'(\d{3,4})', txt)]
    if yrs:
        y=sum(yrs)/len(yrs)
        return -y if bce else y
    return None

for n in nodes:
    y=n.get('year')
    if not isinstance(y,(int,float)):
        y=parse_year(n.get('lore',{}).get('period'))
    n['_year']=y

# 模型平均年代(给无年代者兜底)
myears={}
for code in models_meta:
    ys=[n['_year'] for n in nodes if n['model']==code and n['_year'] is not None]
    myears[code]=sum(ys)/len(ys) if ys else 1500.0
for n in nodes:
    if n['_year'] is None: n['_year']=myears.get(n['model'],1500.0)

# ============ 布局 ============
S=16.0
def norm(P):  # 居中并缩放到 ~[-S,S]
    xs=[p[0] for p in P]; ys=[p[1] for p in P]; zs=[p[2] for p in P]
    cx,cy,cz=sum(xs)/len(xs),sum(ys)/len(ys),sum(zs)/len(zs)
    P=[[p[0]-cx,p[1]-cy,p[2]-cz] for p in P]
    mx=max(1e-6, max(max(abs(p[0]),abs(p[1]),abs(p[2])) for p in P))
    f=S/mx
    return [[round(p[0]*f,3),round(p[1]*f,3),round(p[2]*f,3)] for p in P]

ids=[n['id'] for n in nodes]
idx={i:k for k,i in enumerate(ids)}
N=len(nodes)

# V3 世界观区(6 区, 无东西对称) —— 取代旧 12 模型分组; 东/西降为属性
WV3=json.load(open(os.path.join(DATA,'kg_worldview_v3.json'),encoding='utf-8'))
WVREG=WV3.get('regions',[])
codes=[r['id'] for r in WVREG]                 # WV1..WV6
wvreg={r['id']:r for r in WVREG}
def gkey(n): return n.get('wv') if n.get('wv') in wvreg else codes[0]
for n in nodes:
    if n.get('wv') not in wvreg: n['wv']=codes[0]

# ① 坐标(V3 两轴: 再现-表现 × 结构-感知; 第三维=稳定-流动 仅作景深)
def cdim(n,k): return n['coord'].get(k,0.5)
axis=[[ (cdim(n,'rep_exp')-.5)*2*S, (cdim(n,'struct_perc')-.5)*2*S, -(cdim(n,'sta_flu')-.5)*2*S ] for n in nodes]

# ② 星系团: 6 个世界观区放到 fibonacci 球上, 成员在各自团内小球散布
def fib_sphere(n):
    pts=[]; ga=math.pi*(3-math.sqrt(5))
    for i in range(n):
        y=1-(i/(n-1))*2 if n>1 else 0; r=math.sqrt(max(0,1-y*y)); th=ga*i
        pts.append([math.cos(th)*r,y,math.sin(th)*r])
    return pts
mc={c:p for c,p in zip(codes, fib_sphere(len(codes)))}
Rgal=11.0
cluster=[]
cluster_counts={c:sum(1 for n in nodes if gkey(n)==c) for c in codes}
for n in nodes:
    c=gkey(n); base=mc.get(c,[0,0,0])
    rad=2.2+0.9*math.sqrt(max(1,cluster_counts.get(c,1)))   # 团半径 ∝ 成员数
    # 团内确定性散布
    u=random.random(); v=random.random(); w=random.random()
    rr=rad*(u**(1/3)); th=2*math.pi*v; ph=math.acos(2*w-1)
    off=[rr*math.sin(ph)*math.cos(th), rr*math.cos(ph), rr*math.sin(ph)*math.sin(th)]
    cluster.append([base[0]*Rgal+off[0], base[1]*Rgal+off[1], base[2]*Rgal+off[2]])

# ③ 谱系力导向(真实边) —— 3D 弹簧-斥力 + 东西分臂轻偏
pos=[[random.uniform(-S,S),random.uniform(-S,S),random.uniform(-S,S)] for _ in range(N)]
adj=[[] for _ in range(N)]
for e in edges:
    a,b=idx.get(e['s']),idx.get(e['t'])
    if a is not None and b is not None: adj[a].append(b); adj[b].append(a)
k=S*0.55
ITER=320
for it in range(ITER):
    t=0.10*S*(1-it/ITER)+0.02
    disp=[[0,0,0] for _ in range(N)]
    # 斥力
    for i in range(N):
        xi=pos[i]
        for j in range(i+1,N):
            dx=xi[0]-pos[j][0]; dy=xi[1]-pos[j][1]; dz=xi[2]-pos[j][2]
            d2=dx*dx+dy*dy+dz*dz+1e-4; d=math.sqrt(d2)
            f=(k*k)/d2
            ux,uy,uz=dx/d,dy/d,dz/d
            disp[i][0]+=ux*f; disp[i][1]+=uy*f; disp[i][2]+=uz*f
            disp[j][0]-=ux*f; disp[j][1]-=uy*f; disp[j][2]-=uz*f
    # 引力(沿边)
    for i in range(N):
        for j in adj[i]:
            if j<i: continue
            dx=pos[i][0]-pos[j][0]; dy=pos[i][1]-pos[j][1]; dz=pos[i][2]-pos[j][2]
            d=math.sqrt(dx*dx+dy*dy+dz*dz)+1e-4
            f=(d*d)/k
            ux,uy,uz=dx/d,dy/d,dz/d
            disp[i][0]-=ux*f; disp[i][1]-=uy*f; disp[i][2]-=uz*f
            disp[j][0]+=ux*f; disp[j][1]+=uy*f; disp[j][2]+=uz*f
    # 向心(V3 已取消东西对称, 不再分臂; 让真实关系自己塑形)
    for i in range(N):
        disp[i][0]-=pos[i][0]*0.012; disp[i][1]-=pos[i][1]*0.012; disp[i][2]-=pos[i][2]*0.012
        dl=math.sqrt(sum(c*c for c in disp[i]))+1e-9
        s=min(dl,t)/dl
        pos[i][0]+=disp[i][0]*s; pos[i][1]+=disp[i][1]*s; pos[i][2]+=disp[i][2]*s
force=[p[:] for p in pos]

# ④ 时间螺旋
order=sorted(range(N), key=lambda i: nodes[i]['_year'])
ymin=min(n['_year'] for n in nodes); ymax=max(n['_year'] for n in nodes)
helix=[[0,0,0] for _ in range(N)]
turns=3.0; H=2*S
for rank,i in enumerate(order):
    t=rank/max(1,N-1)
    ang=t*turns*2*math.pi
    rad=4.0+t*S*0.7
    helix[i]=[math.cos(ang)*rad, (t-0.5)*H, math.sin(ang)*rad]

# ⑤ 穹顶星天: 全部落在球壳上, 按 6 个世界观区聚成连续分带(无东西对称)
sphere=[[0,0,0] for _ in range(N)]
order_sph=sorted(range(N), key=lambda i:(codes.index(gkey(nodes[i])), nodes[i]['_year']))
gaS=math.pi*(3-math.sqrt(5))
for rank,i in enumerate(order_sph):
    yy=(rank+0.5)/N; y=1-2*yy
    r=math.sqrt(max(0,1-y*y)); th=gaS*rank
    sphere[i]=[math.cos(th)*r*S, y*S, math.sin(th)*r*S]

# ⑥ 放射星系: 中心亮核, 6 个世界观区各一条旋臂, 成员沿臂按年代外推 + 旋绕
radial=[[0,0,0] for _ in range(N)]
arm_dir={}
for kk,c in enumerate(codes):
    a=2*math.pi*kk/len(codes)
    tilt=0.18*math.sin(kk*1.7)
    arm_dir[c]=(math.cos(a), tilt, math.sin(a))
model_members={c:[i for i in range(N) if gkey(nodes[i])==c] for c in codes}
for c in codes:
    mem=sorted(model_members[c], key=lambda i:nodes[i]['_year'])
    m=len(mem); dx,dy,dz=arm_dir[c]
    for rank,i in enumerate(mem):
        t=(rank+1)/(m+1)
        dist=2.0+t*S*0.95
        swirl=t*2.4   # 旋臂缠绕
        ca,sa=math.cos(swirl),math.sin(swirl)
        # 在臂方向上加缠绕扰动
        px=dx*dist; py=dy*dist*0.6; pz=dz*dist
        # 绕 y 轴轻微旋绕, 制造螺旋臂观感
        rx=px*math.cos(swirl*0.4)-pz*math.sin(swirl*0.4)
        rz=px*math.sin(swirl*0.4)+pz*math.cos(swirl*0.4)
        jit=0.5
        radial[i]=[rx+(((i*7)%5)-2)*jit*0.18, py+(((i*3)%5)-2)*jit*0.18, rz+(((i*11)%5)-2)*jit*0.18]

# ⑦ 时间长河: 东西双轨,x 严格按真实年代(东西同一刻度对齐);同一年并列改"垂直展开",绝不右推漂移
RW=S*4.2
_ys=[nodes[i]['_year'] for i in range(N)]; _ymn=min(_ys); _ymx=max(_ys); _sp=(_ymx-_ymn) or 1
def _yx(y): return ((y-_ymn)/_sp-0.5)*2*RW
river=[[0,0,0] for _ in range(N)]
for region,side in (('west',1.0),('east',-1.0)):
    groups={}
    for i in range(N):
        if nodes[i]['region']!=region: continue
        groups.setdefault(round(nodes[i]['_year']),[]).append(i)
    for ky in sorted(groups):
        grp=sorted(groups[ky], key=lambda i:nodes[i]['id']); n=len(grp); x=_yx(ky)
        for kk,i in enumerate(grp):
            yoff=(kk-(n-1)/2.0)*0.82                 # 同年并列:垂直展开,不动 x
            river[i]=[round(x,3), round(side*S*0.55+yoff,3), round(((kk%5)-2)*0.3,3)]
RIVER_META={'ymin':_ymn,'ymax':_ymx,'half':RW}

axis=norm(axis); cluster=norm(cluster); force=norm(force); helix=norm(helix); sphere=norm(sphere); radial=norm(radial)   # river 不 norm(保持拉宽)

# ---------- 艺术家层(真实代表人物) ----------
art_rich = {}
try:
    aj=json.load(open(ART, encoding='utf-8'))
    for aid,a in (aj.get('artists') or {}).items():
        art_rich[a.get('cn','')]=a
except Exception:
    pass
person_styles={}
for n in nodes:
    for p in (n.get('people') or []):
        person_styles.setdefault(p,set()).add(n['id'])
artists=[]
for name,sids in person_styles.items():
    sids=list(sids)
    member_idx=[idx[s] for s in sids if s in idx]
    if not member_idx: continue
    def mean(layout):
        return [round(sum(layout[m][c] for m in member_idx)/len(member_idx),3) for c in range(3)]
    regs=[nodes[m]['region'] for m in member_idx]
    region='east' if regs.count('east')>=regs.count('west') else 'west'
    wvs=[gkey(nodes[m]) for m in member_idx]
    wv=max(set(wvs),key=wvs.count)
    rich=art_rich.get(name) or art_rich.get(name+'（'+name+'）')
    artists.append({
        'name':name,'region':region,'wv':wv,'styles':sids,'deg':len(sids),
        'rich': bool(rich),
        'aid': (rich or {}).get('id','') if rich else '',     # 详情页 id(可点进 kg-artist.html)
        'headline': (rich or {}).get('headline','') if rich else '',
        'pos':{'axis':mean(axis),'cluster':mean(cluster),'force':mean(force),'helix':mean(helix),'sphere':mean(sphere),'radial':mean(radial),'river':mean(river)}
    })

# ---------- 输出节点 ----------
out_nodes=[]
for i,n in enumerate(nodes):
    out_nodes.append({
        'id':n['id'],'cn':n['cn'],
        'region':n['region'],                      # 东/西 = 文化属性
        'wv':gkey(n),'wv_name':wvreg[gkey(n)].get('name',''),
        'model':n.get('model',''),                 # 旧 12 模型(保留,供风格志链接)
        'conf':n.get('conf',''),
        'year':round(n['_year'],1),'deg':deg.get(n['id'],0),
        'people':n.get('people') or [],
        'desc':(n.get('desc') or n.get('lore',{}).get('essence') or ''),
        'coord':{k:round(float(n['coord'].get(k,0.5)),3) for k in ('rep_exp','struct_perc','sta_flu','east_west')},  # 4 轴:供"个人之星"算距离
        'pos':{'axis':axis[i],'cluster':cluster[i],'force':force[i],'helix':helix[i],'sphere':sphere[i],'radial':radial[i],'river':river[i]}
    })
# V3 世界观区(6)
out_regions=[]
for c in codes:
    r=wvreg[c]
    out_regions.append({'id':c,'name':r.get('name',''),'alt':r.get('alt',''),
                        'q':r.get('q',''),'psy':r.get('psy',''),'essence':r.get('essence',''),
                        'count':cluster_counts.get(c,0),'west':r.get('west',0),'east':r.get('east',0)})

galaxy={
    'meta':{
        'title':'风格星辰大海 · 真实关联底座',
        'note':'星=风格(真实节点)。关联度只用真实美术史关系: 风格志手写的 承自/影响/对抗 + 隶属(→世界模型)。不使用作品共现。4 套布局(坐标/星系团/谱系力导向/时间螺旋)离线预算, 前端切换时补间。',
        'edges_real':len(edges),'nodes':len(out_nodes),'artists':len(artists),
        'edges_by_conf':{c:sum(1 for e in edges if e['c']==c) for c in ('high','med')},
        'layouts':['cluster','force','helix','axis','sphere','radial','river'],
        'river':RIVER_META
    },
    'regions':out_regions,'nodes':out_nodes,'edges':edges,'artists':artists
}
json.dump(galaxy, open(OUT,'w',encoding='utf-8'), ensure_ascii=False, separators=(',',':'))
print('wrote', OUT)
print('nodes',len(out_nodes),'edges',len(edges),'artists',len(artists))
print('edge kinds:', {k:sum(1 for e in edges if e['k']==k) for k in ('parent','influence','against')})
print('year range', round(ymin), '→', round(ymax))
print('size KB', round(os.path.getsize(OUT)/1024,1))
