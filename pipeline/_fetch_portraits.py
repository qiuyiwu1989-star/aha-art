# -*- coding: utf-8 -*-
import os,json,urllib.request,urllib.parse,ssl,io,time,re
os.chdir("/home/ubuntu/users/qiuyiwu/aha-art-demo")
_STOP={'van','von','der','den','del','della','di','de','la','le','el','dos','das','y','the','of'}
def _toks(s):
    return [t for t in re.split(r'[\s,.\-()]+', (s or '').lower()) if len(t)>=3 and t not in _STOP]
def name_match(en, adn):
    et=_toks(en); at=set(_toks(adn))
    if not et or not at: return False
    if et[-1] not in at: return False           # 姓必须整词命中
    if len(et)>=2 and et[0] not in at: return False  # 名也要在(防 Meng↔Mengs 撞)
    return True
from PIL import Image
ctx=ssl.create_default_context();ctx.check_hostname=False;ctx.verify_mode=ssl.CERT_NONE
UA={'User-Agent':'Mozilla/5.0 aha-portrait-research'}
def gj(u,t=15):return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=t,context=ctx).read())
def get(u,t=40):return urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=t,context=ctx).read()
MET="https://collectionapi.metmuseum.org/public/collection/v1"
CLE="https://openaccess-api.clevelandart.org/api/artworks"
LOG=open("_fetch_portraits.log","w")
def L(*a):print(*a,file=LOG,flush=True)
A=json.load(open('data/kg_artists.json'))['artists']
MAN='data/kg_artist_portraits.json'
man=json.load(open(MAN)) if os.path.exists(MAN) else {}
os.makedirs('img/portraits',exist_ok=True)

def good_img(data):
    im=Image.open(io.BytesIO(data));im.load();w,h=im.size
    return (min(w,h)>=300, w,h)

def subj_named(en,title):
    # 标题点名了本人:名字 token 与标题交集≥2,或单个够独特(≥6字母,如 Rembrandt/Leonardo/Cézanne)
    et=set(_toks(en));
    if not et or 'portrait' not in title: return False
    m=et & set(_toks(title))
    return len(m)>=2 or (len(m)==1 and len(next(iter(m)))>=6)

def met_find(en):
    if not _toks(en): return None
    best=None
    for q in [en+' portrait']:
        try: s=gj(MET+"/search?hasImages=true&q="+urllib.parse.quote(q))
        except: continue
        for oid in (s.get('objectIDs') or [])[:12]:
            try: o=gj(MET+f"/objects/{oid}",12)
            except: continue
            if not o.get('isPublicDomain') or not o.get('primaryImageSmall'): continue
            title=(o.get('title') or '').lower(); adn=o.get('artistDisplayName') or ''
            img=o.get('primaryImage') or o.get('primaryImageSmall')
            selfp=('self-portrait' in title or 'self portrait' in title or 'selbstbildnis' in title)
            if selfp and name_match(en,adn):                 # 本人自画像(最佳)
                return (3,o.get('title'),adn,img,'The Met (PD)')
            if best is None and subj_named(en,title):  # 别人画的、标题点名本人
                best=(2,o.get('title'),adn,img,'The Met (PD)')
            time.sleep(.03)
        if best and best[0]==3: break
    return best

def cle_find(en):
    if not _toks(en): return None
    best=None
    try: s=gj(CLE+"?cc0=1&has_image=1&limit=18&q="+urllib.parse.quote(en+' portrait'))
    except: return None
    for a in s.get('data',[]):
        title=(a.get('title') or '')
        cr=' '.join((c.get('description','') for c in (a.get('creators') or []))).lower()
        img=(a.get('images') or {}).get('web',{}).get('url') or (a.get('images') or {}).get('print',{}).get('url')
        if not img: continue
        tl=title.lower()
        if ('self-portrait' in tl or 'self portrait' in tl) and name_match(en,cr):
            return (3,title,(a.get('creators') or [{}])[0].get('description',''),img,'Cleveland (CC0)')
        if best is None and subj_named(en,tl):
            best=(2,title,(a.get('creators') or [{}])[0].get('description',''),img,'Cleveland (CC0)')
    return best

rich=[(k,v) for k,v in A.items() if not v.get('_stub') and v.get('en')]
L("TODO",len(rich)); got=0;done=0
for k,v in rich:
    done+=1
    if k in man: continue
    en=v['en']
    r=met_find(en) or cle_find(en)
    if not r: L("—",v['cn'],"无"); continue
    sc,title,by,img,src=r
    try:
        data=get(img,45); ok,w,h=good_img(data)
        if not ok: L("低清跳过",v['cn'],f"{w}x{h}"); continue
        fp=f"img/portraits/{k.split('.')[-1]}.jpg"
        open(fp,'wb').write(data)
        man[k]={"file":fp,"source":src,"title":title,"by":by,"score":sc,"w":w,"h":h}
        got+=1
        L(f"✅ {v['cn']} 置信{sc} {w}x{h} | {title[:32]} | {src}")
        if got%5==0: json.dump(man,open(MAN,'w'),ensure_ascii=False,indent=1); L("...saved",got)
    except Exception as e:
        L("下载失败",v['cn'],repr(e)[:60])
    time.sleep(.05)
json.dump(man,open(MAN,'w'),ensure_ascii=False,indent=1)
L("DONE 命中",got,"/",len(rich))
LOG.close()
