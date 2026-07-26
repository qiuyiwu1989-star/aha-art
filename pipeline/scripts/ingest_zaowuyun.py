#!/usr/bin/env python3
"""造物云「创意设计」素材库(14k图)→ CLIP分类 → 存COS zaowuyun/<类别>/ → zaowuyun_media。
油画子集额外并入生成区 gen_file(source=zaowuyun,与AI生成图放一起)。元数据全抓。
⚠️ 以文件方式从 scripts/ 跑(import torch,别从 pipeline/ 用 -c,会撞 profile.py)。
用法: python3 ingest_zaowuyun.py [--limit N] [--workers 6]
"""
import os, sys, json, io, time, hashlib, argparse, threading, urllib.request
os.environ.setdefault('MODELSCOPE_CACHE', os.path.expanduser('~/.cache/modelscope'))
import numpy as np, psycopg2, torch
from concurrent.futures import ThreadPoolExecutor, as_completed
from transformers import CLIPModel, CLIPProcessor
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
import imagehash
from qcloud_cos import CosS3Client, CosConfig

CLIP_PATH = "/home/ubuntu/.cache/modelscope/models/openai-mirror/clip-vit-base-patch16"
BUCKET = "aha-1254041526"; COS_ROOT = "zaowuyun/"
ART_PAIR = ["a hand-painted artwork: oil painting, ink/watercolor painting or illustration, with visible brushstrokes (painted, not a photo)",
            "a real camera photograph, a 3D product render, or a flat graphic/logo design (not hand-painted)"]
ART_SUB = [("油画","a realistic oil painting or classical painting: landscape, portrait or figure, with oil-paint brushstrokes and canvas"),
           ("插画","a flat illustration, anime/cartoon drawing, comic or stylized hand-drawn picture")]
PHOTO_SUB = [("产品设计","a product photo or 3D product render on a plain/white background"),
             ("IP设计","a cute character, mascot, figurine or 3D cartoon IP design"),
             ("平面设计","a graphic design, logo, poster, banner or text layout"),
             ("人物实景","a real photograph of a person, fashion model or real-world scene"),
             ("其它","something else")]
def _cfg(p): return json.load(open(os.path.expanduser(p)))
def pg(): d=_cfg("~/.aha_pg.json"); return psycopg2.connect(host=d["host"],port=d["port"],dbname=d["dbname"],user=d["user"],password=d["password"])
_cc=_cfg("~/.aha_cos.json")
def cos_client(): return CosS3Client(CosConfig(Region=_cc["region"],SecretId=_cc["secret_id"],SecretKey=_cc["secret_key"],Timeout=30))
_tls=threading.local()
def cos():
    if not hasattr(_tls,"cl"): _tls.cl=cos_client()
    return _tls.cl

print("加载 CLIP…", flush=True)
M=CLIPModel.from_pretrained(CLIP_PATH); M.eval(); PROC=CLIPProcessor.from_pretrained(CLIP_PATH)
def _enc_text(texts):
    return PROC(text=texts, return_tensors="pt", padding=True)
_T_ART=_enc_text(ART_PAIR); _T_AS=_enc_text([t for _,t in ART_SUB]); _T_PS=_enc_text([t for _,t in PHOTO_SUB])
_mlock=threading.Lock()
def _cls(t_enc, labels, pix):
    with _mlock, torch.no_grad():
        o=M(input_ids=t_enc["input_ids"],attention_mask=t_enc["attention_mask"],pixel_values=pix)
    p=torch.softmax(o.logits_per_image[0],dim=0); c=int(p.argmax()); return labels[c], float(p[c])
def classify(im):
    inp=PROC(images=im, return_tensors="pt"); pix=inp["pixel_values"]
    art_lab,art_conf=_cls(_T_ART,["art","photo"],pix)
    if art_lab=="art":
        cat,conf=_cls(_T_AS,[x[0] for x in ART_SUB],pix); return cat, round(conf,3)
    cat,conf=_cls(_T_PS,[x[0] for x in PHOTO_SUB],pix); return cat, round(conf,3)

def ext_of(url, typ):
    e=url.split("?")[0].rsplit(".",1)[-1].lower()
    if e in ("png","jpg","jpeg","webp"): return e
    return {"image/png":"png","image/jpeg":"jpg","image/webp":"webp"}.get(typ,"jpg")

import http.client, ssl
from urllib.parse import urlsplit, urlunsplit, quote as _q
_SSL=ssl.create_default_context(); _SSL.check_hostname=False; _SSL.verify_mode=ssl.CERT_NONE  # 部分MinIO证书无效
Image.MAX_IMAGE_PIXELS=None  # 解炸弹保护
def _fetch(url):
    p=urlsplit(url.strip())
    u2=urlunsplit((p.scheme,p.netloc,_q(p.path,safe="/%:@"),_q(p.query,safe="=&/%:?"),""))
    req=urllib.request.Request(u2,headers={"User-Agent":"Mozilla/5.0"})
    try: return urllib.request.urlopen(req,timeout=90,context=_SSL).read()
    except http.client.IncompleteRead as e: return e.partial
def process(row):
    src_id,url,typ,disp,meta = row
    try:
        raw=_fetch(url)
        sha=hashlib.sha256(raw).hexdigest()
        im=Image.open(io.BytesIO(raw)); im.load(); w,h=im.size
        rgb=im.convert("RGB")
        cat,conf=classify(rgb)
        ph=str(imagehash.phash(rgb))
        ext=ext_of(url,typ)
        key=f"{COS_ROOT}{src_id}.{ext}"
        cos().put_object(Bucket=BUCKET, Key=key, Body=raw)
        return src_id,dict(cat=cat,conf=round(conf,3),key=key,sha=sha,ph=ph,w=w,h=h,disp=disp,meta=meta,ext=ext),None
    except Exception as e:
        return src_id,None,repr(e)[:80]

def run(limit=None, workers=6):
    cn=pg(); cn.autocommit=False; cur=cn.cursor()
    cur.execute("SELECT src_id,src_url,type,display_name,meta FROM zaowuyun_media WHERE status='pending'"+(f" LIMIT {int(limit)}" if limit else ""))
    rows=cur.fetchall(); print(f"待处理 {len(rows)}", flush=True)
    n=dict(ok=0,err=0); bycat={}; t0=time.time(); lock=threading.Lock()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs=[ex.submit(process,r) for r in rows]
        for done,fut in enumerate(as_completed(futs),1):
            src_id,res,err=fut.result()
            with lock:
                c=cn.cursor()
                if err:
                    n["err"]+=1; c.execute("UPDATE zaowuyun_media SET status='err',meta=meta||%s WHERE src_id=%s",(json.dumps({"err":err}),src_id))
                else:
                    bycat[res["cat"]]=bycat.get(res["cat"],0)+1; n["ok"]+=1
                    c.execute("""UPDATE zaowuyun_media SET category=%s,cls_conf=%s,cos_key=%s,sha256=%s,phash=%s,
                        width=%s,height=%s,status='stored',imported_at=now() WHERE src_id=%s""",
                        (res["cat"],res["conf"],res["key"],res["sha"],res["ph"],res["w"],res["h"],src_id))
                cn.commit()
                if done%200==0:
                    print(f"  {done}/{len(rows)} ok={n['ok']} err={n['err']} {done/(time.time()-t0):.1f}/s  {bycat}",flush=True)
    print(f"\n>>> 完成 ok={n['ok']} err={n['err']} 用时{time.time()-t0:.0f}s\n分类: {bycat}",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--limit",type=int); ap.add_argument("--workers",type=int,default=6)
    a=ap.parse_args(); run(a.limit,a.workers)
