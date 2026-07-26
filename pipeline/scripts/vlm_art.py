#!/usr/bin/env python3
"""用 MIMO(VLM) 给艺术藏品库做中国书画鉴赏式描述标注(非质检)。
读 dam_asset(lib) → VLM 评 题材/技法/意境/主体/画意 → 存:
  · dam_vlm(lib,item_id,data)  完整标注(Inspector 展示)
  · dam_tag_item(source='vlm') 结构化标签(题材/技法/意境/元素/朝代,进标签系统可搜可筛)
路径含 朝代 也顺手抽成标签。幂等增量:跳过已标的。

用法: python3 vlm_art.py --lib guohua [--limit N] [--workers 6]
"""
import os, json, argparse, threading, importlib.util
from concurrent.futures import ThreadPoolExecutor, as_completed
import psycopg2

# 复用 gen_gate 的 mimo 调用 / 取图 / JSON 解析
_spec = importlib.util.spec_from_file_location("gg", os.path.join(os.path.dirname(__file__), "gen_gate.py"))
gg = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(gg)

CN_PROMPT = ('你是中国传统书画鉴赏专家。看这幅画,严格只输出 JSON(中文,不要多余文字):\n'
  '{"genre":"题材,从中选1: 山水/花鸟/人物/走兽/鱼虫/蔬果/书法/其他",\n'
  '"technique":"技法,从中选1: 水墨写意/工笔设色/青绿山水/白描/浅绛/没骨/书法/其他",\n'
  '"subject":"画面主体,一句话",\n'
  '"elements":["画中主要物象3-6个,如:松/鹤/远山/亭台/舟/文士/题跋/印章"],\n'
  '"mood":"意境氛围,2-4字,如:空灵/苍劲/清雅/萧疏/富贵",\n'
  '"caption":"一句话描述画面内容与气韵",\n'
  '"has_calligraphy": true或false}')

WEST_PROMPT = ('你是西方美术史专家。看这幅画,严格只输出 JSON(中文,不要多余文字):\n'
  '{"genre":"题材,从中选1: 风景/人物肖像/静物/宗教神话/风俗场景/裸体/动物/抽象/其他",\n'
  '"technique":"画派风格,从中选1: 古典写实/印象派/后印象派/表现主义/巴洛克/浪漫主义/立体主义/超现实/其他",\n'
  '"subject":"画面主体,一句话",\n'
  '"elements":["画中主要元素3-6个"],\n'
  '"mood":"氛围基调,2-4字,如:静谧/热烈/忧郁/庄严/明快",\n'
  '"caption":"一句话描述画面内容与艺术特色",\n'
  '"has_calligraphy": false}')

WEB_PROMPT = ('你是资深网页/UI 设计鉴赏专家。看这张网页或界面截图,严格只输出 JSON(中文,不要多余文字):\n'
  '{"genre":"页面类型,从中选1: 落地页/作品集/电商/仪表盘/博客/文档/营销/App界面/其他",\n'
  '"technique":"设计风格,从中选1: 极简/大胆排版/暗色/渐变炫彩/拟物/扁平/编辑杂志风/科技感/复古/其他",\n'
  '"subject":"这个页面在做什么,一句话",\n'
  '"elements":["主要设计元素3-6个,如:大标题/网格/卡片/插画/3D/导航栏/CTA按钮/表格"],\n'
  '"mood":"整体气质,2-4字,如:高级/活力/专业/温暖/未来感",\n'
  '"caption":"一句话描述这个页面的设计特点",\n'
  '"has_calligraphy": false}')

DESIGN_PROMPT = ('你是资深视觉设计鉴赏专家。看这张图,严格只输出 JSON(中文,不要多余文字):\n'
  '{"genre":"内容类型,一个词,如: 产品设计/IP角色/包装/插画/海报/图案纹样/人物/场景/logo/其他",\n'
  '"technique":"风格,一个词,如: 3D渲染/扁平插画/写实/国潮/赛博朋克/极简/手绘/像素/其他",\n'
  '"subject":"画面主体,一句话",\n'
  '"elements":["主要元素3-6个"],\n'
  '"mood":"气质基调,2-4字,如: 高级/活泼/科技感/温暖/复古",\n'
  '"caption":"一句话描述这张图的内容与设计特点",\n'
  '"has_calligraphy": false}')

# 库 → 用哪套 prompt
KIND = {"guohua": "cn", "beitie": "cn", "yishujia": "cn", "nianhua": "cn", "artwork": "west",
        "webdesign": "web", "media": "design", "infmonkeys": "design"}
def _prompt_for(lib):
    k = KIND.get(lib)
    return WEST_PROMPT if k == "west" else WEB_PROMPT if k == "web" else DESIGN_PROMPT if k == "design" else CN_PROMPT

def _cfg(p): return json.load(open(os.path.expanduser(p)))
def pg():
    d=_cfg("~/.aha_pg.json"); return psycopg2.connect(host=d["host"],port=d["port"],dbname=d["dbname"],user=d["user"],password=d["password"])

import base64, ssl, urllib.request, urllib.parse
_SSL = ssl.create_default_context(); _SSL.check_hostname = False; _SSL.verify_mode = ssl.CERT_NONE
def _fetch_b64(bucket, cos_key, px=768):
    """桶无关取图:经 dam.alimq.com 代理(aha桶走/img,其它桶走/cimg/<桶>/),base64。"""
    path = ("/img/" + cos_key) if bucket == "aha-1254041526" else (f"/cimg/{bucket}/" + cos_key)
    u = "https://dam.alimq.com" + urllib.parse.quote(path, safe="/") + f"?imageMogr2/thumbnail/{px}x"
    raw = urllib.request.urlopen(u, timeout=40, context=_SSL).read()
    return base64.b64encode(raw).decode()

def _vlm_art(base,key,model,b64,prompt):
    import urllib.request
    msg=[{"role":"user","content":[{"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":b64}},{"type":"text","text":prompt}]}]
    body=json.dumps({"model":model,"max_tokens":4000,"messages":msg}).encode()
    req=urllib.request.Request(base,data=body,method="POST",headers={"content-type":"application/json","x-api-key":key,"anthropic-version":"2023-06-01"})
    with urllib.request.urlopen(req,timeout=300) as r: out=json.loads(r.read())
    txt=" ".join(b.get("text","") for b in out.get("content",[]) if b.get("type")=="text")
    return gg._parse_json(txt)

_CANON_MOOD = ["空灵","苍劲","清雅","萧疏","古朴","雄浑","淡雅","秀润","静谧","幽远","恬淡","雅致","豪迈","富贵","庄重","清幽","沉郁","明快","温润","灵动","宁静","悠远","雄奇","飘逸","肃穆","优雅","神秘","梦幻","高级","活力","专业","温暖","未来感","科技感","复古","时尚","热烈","清新","质朴"]
def canon_moods(tag):
    tag=(tag or "").strip()
    if tag in _CANON_MOOD: return [tag]
    found=[c for c in _CANON_MOOD if c in tag]
    return found if found else [tag]

def _dynasty_from_key(cos_key):
    parts=(cos_key or "").split("/")
    # artworks/国画浏览版/<朝代>/...
    if len(parts)>2 and "国画" in parts[1] and 1<=len(parts[2])<=3:
        return parts[2]
    return None

def _review(args):
    aid,ext_id,bucket,cos_key,base,key,model,prompt=args
    item="a"+str(aid) if not ext_id else ext_id
    try:
        b64=_fetch_b64(bucket,cos_key)   # 桶无关代理取图
    except Exception as e:
        return item,None,cos_key,f"img:{repr(e)[:40]}"
    for a in range(2):
        try:
            v=_vlm_art(base,key,model,b64,prompt)
            if v: return item,v,cos_key,None
        except Exception as e:
            last=repr(e)[:60]
        import time;time.sleep(1.5*(a+1))
    return item,None,cos_key,"fail"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--lib",default="guohua")
    ap.add_argument("--limit",type=int,default=0)
    ap.add_argument("--workers",type=int,default=6)
    a=ap.parse_args()
    base,key,model=gg.mimo_cfg()
    cn=pg(); cur=cn.cursor()
    q=f"""SELECT a.asset_id,a.ext_id,a.bucket,a.cos_key FROM dam_asset a
          WHERE a.lib=%s AND a.status='active'
            AND NOT EXISTS(SELECT 1 FROM dam_vlm v WHERE v.lib=%s AND v.item_id=COALESCE(a.ext_id,'a'||a.asset_id::text))"""
    if a.limit: q+=f" LIMIT {int(a.limit)}"
    cur.execute(q,(a.lib,a.lib)); rows=cur.fetchall()
    print(f"[{a.lib}] 待标注 {len(rows)} 张 (workers={a.workers})",flush=True)
    lock=threading.Lock(); n=dict(ok=0,err=0); import time;t0=time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        prompt=_prompt_for(a.lib)
        futs=[ex.submit(_review,(r[0],r[1],r[2],r[3],base,key,model,prompt)) for r in rows]
        # cos_key 映射(取朝代)
        keymap={("a"+str(r[0]) if not r[1] else r[1]):r[3] for r in rows}
        for done,fut in enumerate(as_completed(futs),1):
            item,v,cos_key,err=fut.result()
            with lock:
                c=cn.cursor()
                if err or not v:
                    n["err"]+=1
                else:
                    c.execute("INSERT INTO dam_vlm(lib,item_id,data) VALUES(%s,%s,%s) ON CONFLICT(lib,item_id) DO UPDATE SET data=EXCLUDED.data",
                              (a.lib,item,json.dumps(v,ensure_ascii=False)))
                    # 结构化标签进标签系统
                    tags=[]
                    if v.get("genre"): tags.append(("题材",v["genre"]))
                    if v.get("technique"): tags.append(("技法",v["technique"]))
                    for _m in (canon_moods(v["mood"]) if v.get("mood") else []): tags.append(("意境",_m))
                    for el in (v.get("elements") or [])[:6]:
                        if el and len(str(el))<=8: tags.append(("元素",str(el)))
                    dyn=_dynasty_from_key(keymap.get(item))
                    if dyn: tags.append(("朝代",dyn))
                    for facet,tag in tags:
                        c.execute("INSERT INTO dam_tag_item(lib,item_id,tag,facet,source,conf) VALUES(%s,%s,%s,%s,'vlm',NULL) ON CONFLICT DO NOTHING",
                                  (a.lib,item,str(tag)[:40],facet))
                    n["ok"]+=1
                cn.commit()
                if done%50==0: print(f"  {done}/{len(rows)} ok={n['ok']} err={n['err']} {done/(time.time()-t0):.2f}/s",flush=True)
    print(f"[{a.lib}] 完成 ok={n['ok']} err={n['err']} 用时{time.time()-t0:.0f}s",flush=True)

if __name__=="__main__": main()
