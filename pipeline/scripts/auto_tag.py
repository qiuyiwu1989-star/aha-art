#!/usr/bin/env python3
"""本地 CLIP 零样本自动打标(零 token / 不联网)。
复用已入库的图像向量(gen_clip.embedding_vec / zaowuyun_media.embedding_vec),
只对候选标签词做一次文本编码,算余弦相似度,每个维度(facet)取最匹配的标签。
写入 dam_tag_item(source='auto')。幂等增量:跳过已有 auto 标签的图。

用法: python3 auto_tag.py [--lib gen|media|both] [--limit N] [--batch 2000] [--min 0.18]
"""
import os, json, argparse
import numpy as np, torch, clip, psycopg2

# 候选标签:每个维度(facet) → { 中文标签 : 英文CLIP提示词 }。英文提示对 ViT-B/32 更准,存中文标签。
FACETS = {
  "题材": {
    "人物":"a portrait of a person","动物":"an animal","产品":"a product object shot",
    "风景":"a landscape scenery","食物":"food and drink","建筑":"a building architecture",
    "植物花卉":"plants and flowers","服装":"clothing apparel fashion","IP角色":"a cute cartoon character mascot",
    "图案纹样":"a seamless decorative pattern","包装":"product packaging design","交通工具":"a vehicle car",
    "珠宝配饰":"jewelry and accessories","场景空间":"an interior space scene",
  },
  "风格": {
    "扁平插画":"a flat vector illustration","写实摄影":"a photorealistic photograph","3D渲染":"a 3d render cgi",
    "水彩":"a watercolor painting","油画":"an oil painting","线稿":"a line art sketch drawing",
    "国风":"chinese traditional ink painting style","赛博朋克":"cyberpunk neon style","极简":"minimalist clean design",
    "像素风":"pixel art","卡通动漫":"cartoon anime style","蒸汽朋克":"steampunk style",
  },
  # 注:色调维度交给已有的 ave_rgb/hue 主色数据(更准),不用 CLIP(读色弱)。
}

def _cfg(p): return json.load(open(os.path.expanduser(p)))
def pg():
    d=_cfg("~/.aha_pg.json"); return psycopg2.connect(host=d["host"],port=d["port"],dbname=d["dbname"],user=d["user"],password=d["password"])

def build_label_matrix(model, device):
    facets, tags, prompts = [], [], []
    for fc, mp in FACETS.items():
        for tag, prm in mp.items():
            facets.append(fc); tags.append(tag); prompts.append(prm)
    tok = clip.tokenize(prompts).to(device)
    with torch.no_grad():
        emb = model.encode_text(tok)
        emb = emb / emb.norm(dim=-1, keepdim=True)
    return np.array(facets), np.array(tags), emb.cpu().numpy().astype(np.float32)  # (L,), (L,), (L,512)

def parse_vec(s):
    return np.fromstring(s.strip()[1:-1], sep=",", dtype=np.float32)

def run_lib(cur, lib, labelmat, facets, tags, a):
    facet_idx = {fc: np.where(facets==fc)[0] for fc in FACETS}   # 每个维度的标签列下标
    params=()
    if lib=="media":
        q=f"""SELECT m.src_id, m.embedding_vec::text FROM zaowuyun_media m
              WHERE m.status='stored' AND m.embedding_vec IS NOT NULL
                AND NOT EXISTS(SELECT 1 FROM dam_tag_item t WHERE t.lib='media' AND t.item_id=m.src_id AND t.source='auto')"""
    elif lib=="gen-legacy":
        q=f"""SELECT gf.instance_id, gc.embedding_vec::text
              FROM gen_file gf JOIN gen_clip gc ON gc.instance_id=gf.instance_id
              WHERE gf.source='zaowuyun_team' AND gf.role='output' AND gc.embedding_vec IS NOT NULL
                AND NOT EXISTS(SELECT 1 FROM dam_tag_item t WHERE t.lib='gen' AND t.item_id=gf.instance_id AND t.source='auto')"""
    else:
        # 统一表(dam_asset+dam_embedding)的任意库;item_id=对外id(ext_id 或 'a'+asset_id),与前端标签筛选一致
        q="""SELECT COALESCE(a.ext_id,'a'||a.asset_id::text) iid, e.embedding::text
             FROM dam_asset a JOIN dam_embedding e USING(asset_id)
             WHERE a.lib=%s AND a.status='active'
               AND NOT EXISTS(SELECT 1 FROM dam_tag_item t WHERE t.lib=%s
                              AND t.item_id=COALESCE(a.ext_id,'a'||a.asset_id::text) AND t.source='auto')"""
        params=(lib, lib)
    if a.limit: q+=f" LIMIT {int(a.limit)}"
    cur.execute(q, params); rows=cur.fetchall()
    print(f"[{lib}] 待打标 {len(rows)} 张", flush=True)
    n=0
    for i in range(0,len(rows),a.batch):
        chunk=rows[i:i+a.batch]
        ids=[r[0] for r in chunk]
        V=np.vstack([parse_vec(r[1]) for r in chunk])           # (B,512)
        V=V/ (np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
        S=V @ labelmat.T                                        # (B,L) 余弦相似度
        recs=[]
        for bi,iid in enumerate(ids):
            for fc,cols in facet_idx.items():
                j=cols[np.argmax(S[bi,cols])]                   # 该维度最匹配标签
                conf=float(S[bi,j])
                if conf>=a.min:
                    recs.append((lib,iid,str(tags[j]),fc,"auto",round(conf,4)))
        if recs:
            cur.executemany("""INSERT INTO dam_tag_item(lib,item_id,tag,facet,source,conf)
                               VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", recs)
            cur.connection.commit()
        n+=len(ids)
        if n % (a.batch*2)==0: print(f"  [{lib}] {n}/{len(rows)}", flush=True)
    print(f"[{lib}] 完成 {n} 张", flush=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--lib",default="both",help="both | 逗号分隔的库名,如 artwork,guohua,nianhua")
    ap.add_argument("--limit",type=int,default=0)
    ap.add_argument("--batch",type=int,default=2000)
    ap.add_argument("--min",type=float,default=0.18)   # 低于此相似度不打(避免硬塞)
    a=ap.parse_args()
    device="cuda" if torch.cuda.is_available() else "cpu"
    print(f"加载 CLIP ViT-B/32 on {device}(本地,零token)…",flush=True)
    model,_=clip.load("ViT-B/32",device=device); model.eval()
    facets,tags,labelmat=build_label_matrix(model,device)
    print(f"候选标签 {len(tags)} 个 / {len(FACETS)} 维度",flush=True)
    cn=pg(); cur=cn.cursor()
    libs=["gen-legacy","media"] if a.lib=="both" else a.lib.split(",")
    for lib in libs: run_lib(cur,lib,labelmat,facets,tags,a)
    cur.close(); cn.close()

if __name__=="__main__": main()
