# -*- coding: utf-8 -*-
import os,json,urllib.request,ssl,io,time,re,unicodedata
os.chdir("/home/ubuntu/users/qiuyiwu/aha-art-demo")
from PIL import Image
ctx=ssl.create_default_context();ctx.check_hostname=False;ctx.verify_mode=ssl.CERT_NONE
UA={'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 Chrome/120 Safari/537.36'}
def get(u,t=20):return urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=t,context=ctx).read()
_STOP={'van','von','der','den','del','della','di','de','la','le','el','dos','das','y','the','of'}
def _toks(s):return [t for t in re.split(r'[\s,.\-()]+',(s or '').lower()) if len(t)>=3 and t not in _STOP]
def slug(en):
    s=unicodedata.normalize('NFKD',en).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+','-',s).strip('-')
def title_ok(en,ogt):
    et=_toks(en); tt=set(_toks(ogt))
    if not et: return False
    if len(et)==1: return et[0] in tt
    return et[-1] in tt and (et[0] in tt or len(et[-1])>=6)   # 姓在(+名在或姓独特)
def is_portrait_url(img,sl):
    low=img.lower(); base=low.split('/')[-1].split('!')[0]
    return ('!portrait' in low or 'self-portrait' in low or '440px' in low
            or '/portrait' in low or base==sl+'.jpg' or base.startswith(sl+'.jpg'))
def wikiart(en):
    sl=slug(en)
    html=None
    for _ in range(2):
        try: html=get(f"https://www.wikiart.org/en/{sl}",20).decode('utf-8','ignore'); break
        except: time.sleep(.6)
    if not html: return None
    mt=re.search(r'<meta property="og:title" content="([^"]+)"',html)
    mi=re.search(r'<meta property="og:image" content="([^"]+)"',html)
    if not mt or not mi: return None
    ogt=mt.group(1); img=mi.group(1)
    if not title_ok(en,ogt): return None         # 防错人
    if not is_portrait_url(img,sl): return None   # 防把作品当头像
    return (sl,ogt,img)

if __name__=='__main__':
    import sys
    A=json.load(open('data/kg_artists.json'))['artists']
    if len(sys.argv)>1 and sys.argv[1]=='test':
        for cn,en in [('莫奈','Claude Monet'),('毕加索','Pablo Picasso'),('列宾','Ilya Repin'),('蒙克','Edvard Munch'),('倪瓒','Ni Zan'),('徐悲鸿','Xu Beihong'),('透纳','J.M.W. Turner'),('波提切利','Sandro Botticelli')]:
            r=wikiart(en); print(f"{cn:<6}",("✅ "+r[2][:64]) if r else "✗ 无头像/作品")
        sys.exit()
    MAN='data/kg_artist_portraits.json'
    man=json.load(open(MAN)) if os.path.exists(MAN) else {}
    LOG=open("_fetch_wikiart.log","w");
    def L(*a):print(*a,file=LOG,flush=True)
    rich=[(k,v) for k,v in A.items() if not v.get('_stub') and v.get('en') and k not in man]
    L("TODO",len(rich)); got=0
    for k,v in rich:
        try:
            r=wikiart(v['en'])
            if not r: L("—",v['cn'],"无"); time.sleep(.05); continue
            sl,ogt,img=r
            data=get(img,30); im=Image.open(io.BytesIO(data)); im.load(); w,h=im.size
            if min(w,h)<160: L("低清",v['cn'],f"{w}x{h}"); continue
            fp=f"img/portraits/{k.split('.')[-1]}.jpg"
            Image.open(io.BytesIO(data)).convert('RGB').save(fp,'JPEG',quality=90)
            man[k]={"file":fp,"source":"WikiArt","title":"WikiArt 艺术家头像","by":"","score":2,"w":w,"h":h}
            got+=1; L(f"✅ {v['cn']} {w}x{h} | {img.split('/')[-1][:40]}")
            if got%8==0: json.dump(man,open(MAN,'w'),ensure_ascii=False,indent=1); L("...saved",got)
        except Exception as e:
            L("ERR",v['cn'],repr(e)[:60])
        time.sleep(.08)
    json.dump(man,open(MAN,'w'),ensure_ascii=False,indent=1)
    L("DONE 新增",got,"| 总头像",len(man))
    LOG.close()
