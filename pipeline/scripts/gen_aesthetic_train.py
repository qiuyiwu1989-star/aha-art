#!/usr/bin/env python3
"""C 线:把人工打分(gen_rating)蒸馏成一个便宜的 CLIP 美学头(对齐你们的审美)。
流程:gen_rating 聚合每图人均分 → CLIP 向量(ModelScope CLIP-B/16 CLS) → 训线性/MLP头 → 交叉验证报相关性 → 存权重。
之后用 gen_aesthetic_score.py(同套向量+权重)给全量图便宜打分,当 VLM 前的软预排序。
⚠️ 必须以文件方式从 scripts/ 跑(`python3 scripts/gen_aesthetic_train.py`),别从 pipeline/ 用 -c 跑(会被 profile.py 撞 cProfile)。
用法: python3 gen_aesthetic_train.py [--min-images 150] [--epochs 600]
"""
import os, sys, json, io, time, argparse, urllib.request, urllib.parse
import numpy as np, psycopg2
os.environ.setdefault('MODELSCOPE_CACHE', os.path.expanduser('~/.cache/modelscope'))
CLIP_PATH = "/home/ubuntu/.cache/modelscope/models/openai-mirror/clip-vit-base-patch16"
EMB_CACHE = os.path.expanduser('~/.cache/gen_clip_emb_cache.npz')

def cfg(p): return json.load(open(os.path.expanduser(p)))
def pg(): d=cfg("~/.aha_pg.json"); return psycopg2.connect(host=d["host"],port=d["port"],dbname=d["dbname"],user=d["user"],password=d["password"])

def load_ratings(min_votes=1):
    cn=pg(); cu=cn.cursor()
    cu.execute("""SELECT cos_key, avg(score)::float a, count(*) n FROM gen_rating GROUP BY 1 HAVING count(*)>=%s""",(min_votes,))
    return cu.fetchall()

def get_clip():
    import torch
    from transformers import CLIPModel, CLIPProcessor
    m=CLIPModel.from_pretrained(CLIP_PATH); m.eval()
    proc=CLIPProcessor.from_pretrained(CLIP_PATH)
    return torch, m, proc

def embed_all(keys):
    """CLIP CLS 向量(768),带磁盘缓存(按 cos_key)。"""
    cache={}
    if os.path.exists(EMB_CACHE):
        d=np.load(EMB_CACHE, allow_pickle=True); cache=dict(zip(d['keys'], d['embs']))
    need=[k for k in keys if k not in cache]
    if need:
        torch,m,proc=get_clip()
        cc=cfg("~/.aha_cos.json"); HOST=f"aha-1254041526.cos.{cc['region']}.myqcloud.com"
        from PIL import Image, ImageFile; ImageFile.LOAD_TRUNCATED_IMAGES=True
        t0=time.time()
        for i,k in enumerate(need):
            try:
                u=f"https://{HOST}/"+urllib.parse.quote(k)+"?imageMogr2/thumbnail/224x"
                im=Image.open(io.BytesIO(urllib.request.urlopen(u,timeout=30).read())).convert("RGB")
                inp=proc(images=im,return_tensors="pt")
                with torch.no_grad(): f=m.get_image_features(**inp)
                v=np.asarray(f).reshape(-1,768)[0]   # CLS 768
                cache[k]=v/np.linalg.norm(v)
            except Exception as e: cache[k]=None
            if i%100==0: print(f"  CLIP 向量 {i}/{len(need)} {i/(time.time()-t0+.1):.1f}/s",flush=True)
        ks=[k for k in cache if cache[k] is not None]
        np.savez(EMB_CACHE, keys=np.array(ks,dtype=object), embs=np.array([cache[k] for k in ks],dtype='float32'))
    return cache

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--min-images",type=int,default=150); ap.add_argument("--epochs",type=int,default=600)
    a=ap.parse_args()
    rows=load_ratings()
    print(f"已评图数(≥1票): {len(rows)}")
    if len(rows) < a.min_images:
        print(f"⚠️ 人工分还不够({len(rows)}<{a.min_images})。先去 gen-rate.html 多打一些,再训。"); return
    import torch
    keys=[r[0] for r in rows]; emb=embed_all(keys)
    X=[]; Y=[]
    for k,avg,n in rows:
        if emb.get(k) is not None: X.append(emb[k]); Y.append(avg)
    X=np.array(X,dtype='float32'); Y=np.array(Y,dtype='float32')
    print(f"训练样本 {len(X)}  人均分 min/mean/max={Y.min():.2f}/{Y.mean():.2f}/{Y.max():.2f}")
    # 5 折交叉验证相关性
    rng=np.random.RandomState(0); idx=rng.permutation(len(X)); folds=np.array_split(idx,5); rs=[]
    Xt=torch.tensor(X); Yt=torch.tensor((Y-Y.mean())/Y.std())
    for f in range(5):
        te=folds[f]; tr=np.concatenate([folds[j] for j in range(5) if j!=f])
        net=torch.nn.Sequential(torch.nn.Linear(768,64),torch.nn.ReLU(),torch.nn.Dropout(0.3),torch.nn.Linear(64,1))
        opt=torch.optim.Adam(net.parameters(),lr=0.003,weight_decay=1e-3)
        for ep in range(a.epochs):
            opt.zero_grad(); p=net(Xt[tr]).squeeze(1); loss=torch.nn.functional.mse_loss(p,Yt[tr]); loss.backward(); opt.step()
        with torch.no_grad(): pte=net(Xt[te]).squeeze(1).numpy()
        rs.append(np.corrcoef(pte, Y[te])[0,1])
    print(f"\n=== 人工分蒸馏 CLIP头 5折相关性 r = {np.mean(rs):.3f} (各折 {[round(x,2) for x in rs]}) ===")
    # 用全量训最终头并保存
    net=torch.nn.Sequential(torch.nn.Linear(768,64),torch.nn.ReLU(),torch.nn.Dropout(0.3),torch.nn.Linear(64,1))
    opt=torch.optim.Adam(net.parameters(),lr=0.003,weight_decay=1e-3)
    for ep in range(a.epochs):
        opt.zero_grad(); p=net(Xt).squeeze(1); loss=torch.nn.functional.mse_loss(p,Yt); loss.backward(); opt.step()
    torch.save({"state":net.state_dict(),"mean":float(Y.mean()),"std":float(Y.std())}, os.path.expanduser("~/.cache/gen_aesthetic_head.pt"))
    print("✓ 已存美学头 ~/.cache/gen_aesthetic_head.pt(r>0.5 可当软预排序;否则继续攒分)")

if __name__=="__main__": main()
