#!/usr/bin/env python3
"""生成图美学过滤 + 评估闸门(对照油画 gate.py,适配 AI 生成图)。
独立作用于 gen_file(role=output)。两段:
  阶段一 prefilter(便宜,无VLM):拉普拉斯方差测模糊 + 纯色/全黑测失败 → 明显垃圾直接 reject,不送VLM。
  阶段二 vlm(最后一道,贵):mimo 评 美学/技术(AI瑕疵)/构图/连贯 → composite → 三路分流。
状态 gen_file.q_status: pending → kept(优质) / archived(有瑕疵保留) / rejected(垃圾,预闸或VLM判)。永不物理删。
用法: python3 gen_gate.py prefilter [--limit N] [--workers 16]
      python3 gen_gate.py vlm [--limit N] [--workers 6]
      python3 gen_gate.py stats
"""
import json, os, io, sys, time, base64, argparse, threading, urllib.request, urllib.parse
import numpy as np, psycopg2
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
from scipy import ndimage

def _cfg(p): return json.load(open(os.path.expanduser(p)))
CC = _cfg("~/.aha_cos.json"); BUCKET = "aha-1254041526"
COS_HOST = f"{BUCKET}.cos.{CC['region']}.myqcloud.com"
def pg():
    d=_cfg("~/.aha_pg.json"); return psycopg2.connect(host=d["host"],port=d["port"],dbname=d["dbname"],user=d["user"],password=d["password"])
def mimo_cfg():
    m=_cfg("~/.aha_mimo.json"); base=m["endpoint"].rstrip("/")
    if not base.endswith("/messages"): base+="/v1/messages"
    return base, m["key"], m["model"]

# ---------- 阈值(可 env 调) ----------
SHARP_MIN = float(os.environ.get("GEN_SHARP_MIN", "12"))   # 拉普拉斯方差下限,低于=糊
STD_MIN   = float(os.environ.get("GEN_STD_MIN", "6"))      # 全图颜色标准差下限,低于=纯色/失败

def _thumb(cos_key, px=512):
    url=f"https://{COS_HOST}/"+urllib.parse.quote(cos_key)+f"?imageMogr2/thumbnail/{px}x"
    raw=urllib.request.urlopen(url,timeout=40).read()
    return Image.open(io.BytesIO(raw))

# ========== 阶段一:模糊/失败 预过滤(无 VLM) ==========
def _measure(cos_key):
    im=_thumb(cos_key).convert("RGB")
    g=np.asarray(im.convert("L"),dtype=float)
    sharp=float(ndimage.laplace(g).var())          # 拉普拉斯方差=锐度,越低越糊
    std=float(np.asarray(im,dtype=float).std())     # 颜色标准差,越低越接近纯色
    return sharp, std

def prefilter(limit=None, workers=16, dry=False):
    cn=pg(); cn.autocommit=True; cur=cn.cursor()
    cur.execute(f"SELECT cos_key FROM gen_file WHERE role='output' AND q_status='pending' AND sharpness IS NULL ORDER BY gen_file_id"+(f" LIMIT {int(limit)}" if limit else ""))
    keys=[r[0] for r in cur.fetchall()]
    print(f"[prefilter] 待测 {len(keys)} (SHARP_MIN={SHARP_MIN} STD_MIN={STD_MIN}{' DRY' if dry else ''})",flush=True)
    lock=threading.Lock(); n=dict(blur=0,blank=0,pass_=0,err=0); t0=time.time(); samp=[]
    def one(k):
        try: return k,_measure(k),None
        except Exception as e: return k,None,repr(e)[:60]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for done,(k,m,err) in enumerate(ex.map(one,keys),1):
            with lock:
                if err: n["err"]+=1; continue
                sharp,std=m
                if len(samp)<200: samp.append((sharp,std))
                reason=None
                if std<STD_MIN: reason="blank"      # 纯色/失败
                elif sharp<SHARP_MIN: reason="blurry"
                if dry:
                    n["blank" if reason=="blank" else "blur" if reason=="blurry" else "pass_"]+=1
                else:
                    c2=cn.cursor()
                    if reason:
                        c2.execute("UPDATE gen_file SET sharpness=%s,q_status='rejected',reject_reason=%s,reviewed_at=now() WHERE cos_key=%s",(sharp,reason,k))
                        n["blank" if reason=="blank" else "blur"]+=1
                    else:
                        c2.execute("UPDATE gen_file SET sharpness=%s WHERE cos_key=%s",(sharp,k))
                        n["pass_"]+=1
                if done%200==0: print(f"  {done}/{len(keys)} {done/(time.time()-t0):.0f}/s pass={n['pass_']} blur={n['blur']} blank={n['blank']}",flush=True)
    if samp:
        ss=sorted(x[0] for x in samp)
        print(f"  锐度分位 p5={ss[len(ss)//20]:.0f} p25={ss[len(ss)//4]:.0f} p50={ss[len(ss)//2]:.0f} p95={ss[len(ss)*19//20]:.0f}")
    print(f"[prefilter] 完成 pass={n['pass_']} blur={n['blur']} blank={n['blank']} err={n['err']} 用时{time.time()-t0:.0f}s",flush=True)

# ========== 阶段二:VLM 美学评估(最后一道) ==========
GEN_PROMPT = (
"你是 AI 生成艺术作品的美学与质量评审。看图,严格只输出 JSON(中文),不要多余文字:\n"
'{"category":"严格从这些英文键选1: excellent(成品级,可作为代表作展示) good(质量合格可用) flawed(有明显AI瑕疵:畸形手脚/扭曲面部/解剖错误/物体融化/文字乱码/结构拼接错位) chaotic(构图混乱/语义不通/风格崩坏) garbage(模糊/噪点/纯色块/明显失败生成)",\n'
'"scores":{"aesthetic":0到1美感与艺术性,"technical":0到1技术完成度(无AI瑕疵、细节正确),"composition":0到1构图与视觉平衡,"coherence":0到1画面连贯性与语义合理},\n'
'"artifacts":["列出发现的具体瑕疵(中文短语),没有则空数组"],\n'
'"subject":"画面主题(一句话)","note":"一句话总评"}\n'
"判定从严:有畸形手/脸或解剖错误=flawed;构图崩坏/语义不通=chaotic;模糊噪点纯色=garbage。只看图本身的成像质量与美学,不臆测提示词。"
)
def _parse_json(txt):
    txt=txt.strip()
    if txt.startswith("```"): txt=txt.split("```")[1].lstrip("json").strip() if "```" in txt[3:] else txt[3:]
    i,j=txt.find("{"),txt.rfind("}")
    if i<0 or j<0: return None
    try: return json.loads(txt[i:j+1])
    except Exception: return None
def _img_b64(cos_key, max_px=768):
    im=_thumb(cos_key,max_px).convert("RGB"); im.thumbnail((max_px,max_px))
    bf=io.BytesIO(); im.save(bf,"JPEG",quality=85)
    return base64.b64encode(bf.getvalue()).decode()
def _vlm_call(base,key,model,b64,max_tokens=4000,timeout=300):
    msg=[{"role":"user","content":[{"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":b64}},{"type":"text","text":GEN_PROMPT}]}]
    body=json.dumps({"model":model,"max_tokens":max_tokens,"messages":msg}).encode()
    req=urllib.request.Request(base,data=body,method="POST",headers={"content-type":"application/json","x-api-key":key,"anthropic-version":"2023-06-01"})
    with urllib.request.urlopen(req,timeout=timeout) as r: out=json.loads(r.read())
    txt=" ".join(b.get("text","") for b in out.get("content",[]) if b.get("type")=="text")
    return _parse_json(txt)
def _review_one(args):
    key,base,kk,model=args
    try: b64=_img_b64(key)
    except Exception as e: return key,None,f"img:{repr(e)[:50]}"
    last="parse_fail"
    for a in range(2):
        try:
            v=_vlm_call(base,kk,model,b64)
            if v: return key,v,None
        except Exception as e: last=repr(e)[:70]
        time.sleep(1.5*(a+1))
    return key,None,last
CAT2ST={"excellent":"kept","good":"kept","flawed":"archived","chaotic":"archived","garbage":"rejected"}
def _f(x):
    try: return max(0.0,min(1.0,float(x)))
    except Exception: return 0.0
def vlm(limit=None, workers=6, source=None):
    base,kk,model=mimo_cfg()
    cn=pg(); cur=cn.cursor()
    src = f" AND source='{source}'" if source and source.replace('_','').isalnum() else ""
    cur.execute(f"SELECT cos_key FROM gen_file WHERE role='output' AND q_status='pending' AND sharpness IS NOT NULL{src} ORDER BY gen_file_id"+(f" LIMIT {int(limit)}" if limit else ""))
    keys=[r[0] for r in cur.fetchall()]
    print(f"[vlm] {len(keys)} 张待评 (workers={workers})",flush=True)
    lock=threading.Lock(); n=dict(kept=0,archived=0,rejected=0,err=0); t0=time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs=[ex.submit(_review_one,(k,base,kk,model)) for k in keys]
        for done,fut in enumerate(as_completed(futs),1):
            key,v,err=fut.result()
            with lock:
                c=cn.cursor()
                if err:
                    n["err"]+=1; c.execute("UPDATE gen_file SET reviewed_at=now(),reject_reason=%s WHERE cos_key=%s",(f"vlm_err:{err}"[:80],key))
                else:
                    sc=v.get("scores") or {}
                    comp=round(0.4*_f(sc.get("aesthetic"))+0.3*_f(sc.get("technical"))+0.2*_f(sc.get("composition"))+0.1*_f(sc.get("coherence")),3)
                    v["composite"]=comp
                    st=CAT2ST.get(v.get("category"),"archived")
                    c.execute("UPDATE gen_file SET q_status=%s,quality=%s,vlm=%s,reject_reason=%s,reviewed_at=now() WHERE cos_key=%s",
                              (st,comp,json.dumps(v,ensure_ascii=False),None if st!="rejected" else v.get("category"),key))
                    n[st]+=1
                cn.commit()
                if done%50==0: print(f"  {done}/{len(keys)} kept={n['kept']} arch={n['archived']} rej={n['rejected']} err={n['err']} {done/(time.time()-t0):.2f}/s",flush=True)
    print(f"[vlm] 完成 kept={n['kept']} archived={n['archived']} rejected={n['rejected']} err={n['err']} 用时{time.time()-t0:.0f}s",flush=True)

def stats():
    cn=pg(); cur=cn.cursor()
    cur.execute("SELECT q_status,count(*) FROM gen_file WHERE role='output' GROUP BY 1 ORDER BY 2 DESC")
    print("q_status:",dict(cur.fetchall()))
    cur.execute("SELECT reject_reason,count(*) FROM gen_file WHERE q_status='rejected' GROUP BY 1 ORDER BY 2 DESC")
    print("rejected 原因:",dict(cur.fetchall()))
    cur.execute("SELECT round(avg(quality)::numeric,3),round(min(quality)::numeric,3),round(max(quality)::numeric,3) FROM gen_file WHERE quality IS NOT NULL")
    print("composite 均/最低/最高:",cur.fetchone())
    cur.execute("SELECT vlm->>'category',count(*) FROM gen_file WHERE vlm IS NOT NULL GROUP BY 1 ORDER BY 2 DESC")
    print("VLM category:",dict(cur.fetchall()))

if __name__=="__main__":
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd")
    p=sub.add_parser("prefilter"); p.add_argument("--limit",type=int); p.add_argument("--workers",type=int,default=16); p.add_argument("--dry",action="store_true")
    p=sub.add_parser("vlm"); p.add_argument("--limit",type=int); p.add_argument("--workers",type=int,default=6); p.add_argument("--source",default=None)
    sub.add_parser("stats")
    a=ap.parse_args()
    if a.cmd=="prefilter": prefilter(a.limit,a.workers,a.dry)
    elif a.cmd=="vlm": vlm(a.limit,a.workers,a.source)
    elif a.cmd=="stats": stats()
    else: ap.print_help()
