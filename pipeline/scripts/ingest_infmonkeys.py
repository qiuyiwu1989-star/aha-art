#!/usr/bin/env python3
"""InfMonkeys「艺术家」AI 生成平台 → 独立生成 zone(gen_run / gen_file)。
API artist.infmonkeys.com 本机需:阿里DNS解到 180.163.146.10(getaddrinfo打补丁)+ verify=False(证书链不全)。
图床 minio-infmonkeys.d.run 正常可达。生成数据单独管理,绝不进 works/files/v_ledger。
用法: python3 ingest_infmonkeys.py [--workflow 灵感生成|all] [--limit N] [--page-size 50]
"""
import json, os, sys, time, hashlib, io, socket, argparse, urllib3
import requests, psycopg2
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
import imagehash
from qcloud_cos import CosS3Client, CosConfig
urllib3.disable_warnings()

API_HOST = "artist.infmonkeys.com"; API_IP = "180.163.146.10"
BASE = f"https://{API_HOST}"
TOKEN = "sk-p47tZseNM3LhbY5CU7wFqhGuhJKqOMcz7yNQgn6R8kltktMU"
COS_PREFIX = "artworks/_generated/infmonkeys/"
WORKFLOWS = {  # 中文名 -> workflow id
 "灵感生成":"68a2bc35e540f917535b0256","局部修改":"68a2bcbb77204c13ef155eed","画面分析":"68a2c5fe9be7dbe32a151498",
 "风格迁移":"68a2c66fe5edca9a17ca3c13","主体抠图":"68d248a5feb18b805df4ae16","融合生成":"68d24e1cd95d26ec5f4ba5e5",
 "全局修改":"68d26424db98d06caa1ad998","外延扩图":"68d265661bdb592ffebbf784","高清放大":"68d266515b67b4c79fb85242",
 "视角微调":"68d26703c11f6e582aad878a","中式构图":"68ff17c932dfcbca7fa10f8f","线稿生图":"68ff4cd5f07a793bd067f78d",
 "方案构思":"68ff5758f70cae7ac6e9484f","提取线稿":"69048e4a8d124be4f26c118d","风格分析":"69048fe73038e4582fb606df",
 "画外音分析":"6904921e9d64d1ab2bdd4990"}
WID2NAME = {v:k for k,v in WORKFLOWS.items()}

# --- DNS 补丁:把 artist.infmonkeys.com 钉到阿里DNS解出的IP ---
_orig=socket.getaddrinfo
def _patched(host,*a,**k):
    return _orig(API_IP if host==API_HOST else host,*a,**k)
socket.getaddrinfo=_patched

def _cfg(p): return json.load(open(os.path.expanduser(p)))
S = requests.Session(); S.verify=False
S.headers.update({"Authorization":f"Bearer {TOKEN}","Content-Type":"application/json"})
_cc=_cfg("~/.aha_cos.json")
COS=CosS3Client(CosConfig(Region=_cc["region"],SecretId=_cc["secret_id"],SecretKey=_cc["secret_key"],Timeout=30))
BUCKET="aha-1254041526"
def pg(): d=_cfg("~/.aha_pg.json");return psycopg2.connect(host=d["host"],port=d["port"],dbname=d["dbname"],user=d["user"],password=d["password"])

def search(wid, page, limit):
    r=S.post(f"{BASE}/api/workflow/executions/search", json={"workflowId":wid,"summaryOnly":True,
        "pagination":{"page":page,"limit":limit},"orderBy":{"field":"startTime","order":"DESC"}}, timeout=40)
    return r.json()["data"]

def detail(instance_id):
    r=S.get(f"{BASE}/api/workflow/executions/{instance_id}", timeout=60)
    return r.json()["data"]

import re
IMG_RE=re.compile(r'https?://[^\s"\\]+?\.(?:png|jpg|jpeg|webp)', re.I)
def find_urls(o): return IMG_RE.findall(o if isinstance(o,str) else json.dumps(o,ensure_ascii=False))

_PARAM_KEYS=('seed','steps','cfg','sampler_name','scheduler','denoise','ckpt_name','width','height','batch_size')
def _parse_waj(waj):
    """从 comfyui workflow_api_json(ComfyUI 图)挖生成参数"""
    if isinstance(waj,str):
        try: waj=json.loads(waj)
        except Exception: return {}
    found={}
    def walk(o):
        if isinstance(o,dict):
            for k,v in o.items():
                if k in _PARAM_KEYS and not isinstance(v,(dict,list)): found[k]=v
                else: walk(v)
        elif isinstance(o,list):
            for v in o: walk(v)
    walk(waj); return found

def extract(da):
    """抽:原始词/优化后词/系统词/输入图/输出图/真seed/生成参数(模型·步数·cfg·采样器·尺寸·LLM·token)"""
    tasks=da.get("tasks",[]) or []
    gt=[t for t in tasks if t.get("taskType")=="third_party_api:generate_text"]
    cf=[t for t in tasks if t.get("taskType")=="comfyui:run_comfyui_workflow"]
    input_prompt=final_prompt=system_prompt=llm_model=None; input_imgs=[]; tokens=None
    if gt:
        idata=gt[0].get("inputData") or {}
        input_prompt=idata.get("userMessage"); system_prompt=idata.get("systemPrompt"); llm_model=idata.get("model")
        input_imgs=find_urls(idata.get("userImageMessage") or "")
        odata=gt[0].get("outputData") or {}
        msg=odata.get("message")
        final_prompt=msg if isinstance(msg,str) else (json.dumps(msg,ensure_ascii=False) if msg else None)
        u=odata.get("usage") or {}
        if u: tokens={"in":u.get("prompt_tokens"),"out":u.get("completion_tokens"),"total":u.get("total_tokens")}
    gp={}; out_imgs=[]
    for c in cf:
        gp.update(_parse_waj((c.get("inputData") or {}).get("workflow_api_json")))
        for f in (c.get("outputData") or {}).get("file_list",[]) or []:
            u=f.get("url") if isinstance(f,dict) else f
            if u: out_imgs.append(u)
    if not out_imgs: out_imgs=find_urls(da.get("output") or {})
    if not input_imgs: input_imgs=find_urls(da.get("input") or {})
    # 兜底:正常路径没抽到输出图,扫全文捞 minio 出图 URL(comfyui 出图路径含 /comfyui/),排除输入图
    if not out_imgs:
        cand=[u for u in find_urls(da) if "/comfyui/" in u and u not in input_imgs]
        out_imgs=cand
    wf_type=(da.get("input") or {}).get("workflow_type")
    real_seed=str(gp.get("seed")) if gp.get("seed") is not None else (str((da.get("input") or {}).get("seed") or "") or None)
    params={"model":wf_type,"ckpt":gp.get("ckpt_name"),"seed":gp.get("seed"),"steps":gp.get("steps"),
            "cfg":gp.get("cfg"),"sampler":gp.get("sampler_name"),"scheduler":gp.get("scheduler"),
            "width":gp.get("width"),"height":gp.get("height"),"llm_model":llm_model,"tokens":tokens}
    def dedup(L):
        s=set();o=[]
        for x in L:
            if x not in s: s.add(x);o.append(x)
        return o
    return {"input_prompt":input_prompt,"final_prompt":final_prompt,"system_prompt":system_prompt,
            "input_images":dedup(input_imgs),"output_images":dedup(out_imgs),"seed":real_seed,"params":params}

def fetch_img(url,cur):
    raw=requests.get(url,timeout=60,verify=False).content
    sha=hashlib.sha256(raw).hexdigest()
    cur.execute("SELECT cos_key FROM gen_file WHERE sha256=%s LIMIT 1",(sha,))
    e=cur.fetchone()
    if e: return None,sha,e[0]   # 已存在
    im=Image.open(io.BytesIO(raw)); im.load(); w,h=im.size
    ph=str(imagehash.phash(im.convert("RGB")))
    ext=(url.rsplit(".",1)[-1].split("?")[0] or "png").lower()
    return (raw,sha,ph,w,h,ext),sha,None

def run(workflow, limit, page_size):
    names=[workflow] if workflow!="all" else list(WORKFLOWS)
    cn=pg(); cn.autocommit=False; cur=cn.cursor()
    n_run=n_img=n_dup=n_skip=n_err=0; t0=time.time()
    for name in names:
        wid=WORKFLOWS[name]; page=1; got=0
        total=search(wid,1,1)["total"]; print(f"[{name}] total={total}",flush=True)
        while True:
            d=search(wid,page,page_size); items=d["data"]
            if not items: break
            for it in items:
                if limit and got>=limit: break
                inst=it["workflowId"]   # 注意:这字段实际是实例ID
                cur.execute("SELECT 1 FROM gen_run WHERE instance_id=%s",(inst,))
                if cur.fetchone(): n_skip+=1; got+=1; continue
                try:
                    da=detail(inst); ex=extract(da)
                    cur.execute("""INSERT INTO gen_run(instance_id,workflow_id,workflow_name,status,
                        input_prompt,final_prompt,system_prompt,input_images,seed,params,start_time,end_time,raw)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,to_timestamp(%s/1000.0),to_timestamp(%s/1000.0),%s)
                        ON CONFLICT(instance_id) DO NOTHING""",
                        (inst,wid,name,it.get("status"),ex["input_prompt"],ex["final_prompt"],ex["system_prompt"],
                         json.dumps(ex["input_images"],ensure_ascii=False),ex["seed"],
                         json.dumps(ex["params"],ensure_ascii=False),
                         it.get("startTime"),it.get("endTime"),json.dumps({"tasks_n":len(da.get('tasks',[]))})))
                    n_run+=1
                    for role,urls in [("output",ex["output_images"]),("input",ex["input_images"])]:
                        for u in urls:
                            try:
                                res,sha,exist=fetch_img(u,cur)
                                if exist: n_dup+=1; continue
                                raw,sha,ph,w,h,ext=res
                                key=f"{COS_PREFIX}{name}/{sha}.{ext}"
                                COS.put_object(Bucket=BUCKET,Key=key,Body=raw)
                                cur.execute("""INSERT INTO gen_file(instance_id,cos_key,src_url,sha256,phash,width,height,bytes,fmt,role)
                                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(cos_key) DO NOTHING""",
                                    (inst,key,u,sha,ph,w,h,len(raw),ext,role))
                                n_img+=1
                            except Exception as e: n_err+=1; print("  img err",str(e)[:60],flush=True)
                    cn.commit(); got+=1
                except Exception as e:
                    cn.rollback(); n_err+=1; print("  run err",inst,str(e)[:80],flush=True)
            if limit and got>=limit: break
            if page*page_size>=d["total"]: break
            page+=1
        print(f"[{name}] done got={got}",flush=True)
    print(f"\n>>> 完成 runs={n_run} imgs={n_img} dup={n_dup} skip={n_skip} err={n_err} 用时{time.time()-t0:.0f}s",flush=True)

def enrich(limit=None):
    """对已入库但缺 params 的 gen_run 重新拉 detail,补生成参数/系统词/真seed(幂等)"""
    cn=pg(); cn.autocommit=False; cur=cn.cursor()
    cur.execute("SELECT instance_id FROM gen_run WHERE params IS NULL ORDER BY created_at"+(f" LIMIT {int(limit)}" if limit else ""))
    ids=[r[0] for r in cur.fetchall()]; print(f"待富化 {len(ids)}",flush=True); n=0; t0=time.time()
    for inst in ids:
        try:
            ex=extract(detail(inst))
            cur.execute("""UPDATE gen_run SET params=%s,system_prompt=%s,seed=%s,
                final_prompt=COALESCE(%s,final_prompt),input_prompt=COALESCE(%s,input_prompt)
                WHERE instance_id=%s""",
                (json.dumps(ex["params"],ensure_ascii=False),ex["system_prompt"],ex["seed"],
                 ex["final_prompt"],ex["input_prompt"],inst))
            cn.commit(); n+=1
            if n%100==0: print(f"  {n}/{len(ids)}  {n/(time.time()-t0):.1f}/s",flush=True)
        except Exception as e:
            cn.rollback(); print("  err",inst,str(e)[:60],flush=True)
    print(f">>> 富化完成 {n}",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--workflow",default="灵感生成"); ap.add_argument("--limit",type=int); ap.add_argument("--page-size",type=int,default=50)
    ap.add_argument("--enrich",action="store_true",help="只补已入库记录的 params,不爬新")
    a=ap.parse_args()
    if a.enrich: enrich(a.limit)
    else: run(a.workflow,a.limit,a.page_size)
