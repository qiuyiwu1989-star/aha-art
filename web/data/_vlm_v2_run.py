# -*- coding: utf-8 -*-
# VLM V2 全链提取:用户6维系统描述 + 情绪量化。一次看图填满 L1题材/L2语言/L3情绪/L4画外音+风格+画面动力学。
# 增量写 kg_artwork_v2.jsonl,可断点续。批跑在 main(),import 不触发。
import json, urllib.request, base64, os, time, re
BASE="https://token-plan-cn.xiaomimimo.com/anthropic/v1/messages"
KEY="tp-cwxhnnn1oh0fzpm0h8uk8mey7342gfalfj3qev0p5nmpnbhv"
MODEL="mimo-v2.5"
IMGDIR="/data/pub/p/aha/img/"
OUT="kg_artwork_v2.jsonl"
ANCHORS="喜悦 鲜活 热烈 崇高 张力 恐惧 神秘 忧伤 孤独 怀旧 虚无 沉思 平静 空灵"
PROMPT=("预设你是一位艺术界大师 + 情绪分析师。看这张绘画,做'6维系统描述',只输出一个 JSON(不要解释/不要代码块):\n"
"{\n"
'"media":"①绘画类型:媒介/工艺",\n'
'"subject":"②画面题材:肖像/风景/花卉/叙事等",\n'
'"subject_tags":["②题材关键词2-4个,用于挂题材库"],\n'
'"style":{"流派":"","审美倾向":"","表现特征":""},\n'
'"reading":{"focus_top3":[{"what":"视觉重心","where":"位置","why":"为何吸睛"}],"path":"阅读路径 从…→…→…","guide":"引导手段","elements":["画面关键元素"]},\n'
'"language7":{\n'
'  "构图与组织":{"desc":"技法+现象","v":明显程度0到1},\n'
'  "形状与造型":{"desc":"","v":0到1},\n'
'  "透视与空间":{"desc":"","v":0到1},\n'
'  "色彩系统":{"desc":"","v":0到1},\n'
'  "笔触与肌理":{"desc":"","v":0到1},\n'
'  "边缘与节奏":{"desc":"","v":0到1},\n'
'  "光影与明暗":{"desc":"","v":0到1}},\n'
'"affect":{"vad":{"valence":0到1,"arousal":0到1,"dominance":0到1},'
f'"primary_anchor":"从14锚点选1: {ANCHORS}",'
'"channels":{"构图姿态":"构图/姿态/视线如何推动情绪","题材语义":"题材或符号的情绪含义","光色":"光与色的情绪"},'
'"evidence":["情绪判断的3条关键依据"],"confidence":0到1},\n'
'"voiceover":"⑥画外音:一句有意象但不矫情的旁白",\n'
'"fused":"把①-⑥串成一条不分段的长句自然语言画面描述"\n'
"}\n"
"language7 的 v=该视觉语言在画面里的明显程度。VAD 基于画面证据、勿只看颜色。")
def call(b64, max_tokens=3500):
    msg=[{"role":"user","content":[{"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":b64}},{"type":"text","text":PROMPT}]}]
    body=json.dumps({"model":MODEL,"max_tokens":max_tokens,"messages":msg}).encode()
    req=urllib.request.Request(BASE,data=body,method="POST",headers={"content-type":"application/json","x-api-key":KEY,"anthropic-version":"2023-06-01"})
    with urllib.request.urlopen(req,timeout=240) as r: out=json.loads(r.read())
    txt=' '.join(b.get('text','') for b in out.get('content',[]) if b.get('type')=='text').strip()
    return txt
def parse_json(txt):
    i=txt.find('{'); j=txt.rfind('}')
    if i<0 or j<0: return None
    s=txt[i:j+1]
    try: return json.loads(s)
    except Exception:
        s2=re.sub(r',\s*}','}',re.sub(r',\s*]',']',s))
        try: return json.loads(s2)
        except Exception: return None
def main():
    AW=json.load(open('artworks.json',encoding='utf-8'))
    done=set()
    if os.path.exists(OUT):
        for line in open(OUT,encoding='utf-8'):
            try:
                r=json.loads(line)
                if r.get('v2'): done.add(r['slug'])
            except Exception: pass
    todo=[w for w in AW if w['slug'] not in done and os.path.exists(IMGDIR+w['slug']+'.jpg')]
    print(f"已完成 {len(done)} | 待跑 {len(todo)}",flush=True)
    ok=err=0
    with open(OUT,'a',encoding='utf-8') as f:
        for k,w in enumerate(todo):
            slug=w['slug']; b64=base64.b64encode(open(IMGDIR+slug+'.jpg','rb').read()).decode()
            rec={"slug":slug,"title":w.get('title'),"artist":w.get('artist')}; parsed=None
            for attempt in range(4):
                try:
                    parsed=parse_json(call(b64))
                    if parsed: break
                    time.sleep(1)
                except Exception as e:
                    rec["error"]=repr(e)[:120]; time.sleep(2)
            if parsed: rec["v2"]=parsed; rec.pop("error",None); ok+=1
            else: rec.setdefault("error","parse_fail"); err+=1
            f.write(json.dumps(rec,ensure_ascii=False)+"\n"); f.flush()
            if (k+1)%10==0: print(f"  {k+1}/{len(todo)} ok={ok} err={err}",flush=True)
            time.sleep(0.3)
    print(f"完成 ok={ok} err={err}",flush=True)
if __name__=='__main__': main()
