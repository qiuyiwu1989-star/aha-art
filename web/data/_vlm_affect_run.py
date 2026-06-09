# -*- coding: utf-8 -*-
# 多通道情绪取证:VLM 对 119 幅真图输出结构化 VAD + 三通道理由 + 证据链。
# 增量写 kg_affect_vlm.jsonl,可断点续跑。独立于像素/语料 mood(防循环)。
# 批跑在 main() 里,import 本模块不会触发(只取 call/parse_json)。
import json, urllib.request, base64, os, time, re
BASE="https://token-plan-cn.xiaomimimo.com/anthropic/v1/messages"
KEY="tp-cwxhnnn1oh0fzpm0h8uk8mey7342gfalfj3qev0p5nmpnbhv"
MODEL="mimo-v2.5"
IMGDIR="/data/pub/p/aha/img/"
OUT="kg_affect_vlm.jsonl"
ANCHORS="喜悦 鲜活 热烈 崇高 张力 恐惧 神秘 忧伤 孤独 怀旧 虚无 沉思 平静 空灵"
PROMPT=("你是艺术情绪分析师。看这幅画,只输出一个 JSON(不要任何解释/代码块),字段:\n"
"{\n"
'"scene":"一句话画面内容",\n'
'"vad":{"valence":愉悦度0到1,"arousal":唤起度0到1,"dominance":支配/力量感0到1},\n'
f'"primary_anchor":"从这14个里选最贴切的一个: {ANCHORS}",\n'
'"ch_composition":"构图/人物姿态/表情/视线 如何推动情绪(无人物则说场景动势与空间)",\n'
'"ch_subject":"画的关键题材或符号 及其情绪含义(如骷髅=死亡/十字=信仰)",\n'
'"ch_lightcolor":"光线与色彩给人的情绪",\n'
'"evidence":["让你做出该情绪判断的3条最关键依据"],\n'
'"confidence":0到1的自评可信度\n'
"}\n"
"VAD 三值要相互独立、基于画面证据,不要只看颜色。")
def call(data_b64, max_tokens=2000):
    msg=[{"role":"user","content":[
        {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":data_b64}},
        {"type":"text","text":PROMPT}]}]
    body=json.dumps({"model":MODEL,"max_tokens":max_tokens,"messages":msg}).encode()
    req=urllib.request.Request(BASE,data=body,method="POST",headers={
        "content-type":"application/json","x-api-key":KEY,"anthropic-version":"2023-06-01"})
    with urllib.request.urlopen(req,timeout=180) as r:
        out=json.loads(r.read())
    txt=' '.join(b.get('text','') for b in out.get('content',[]) if b.get('type')=='text').strip()
    return txt,out.get('usage',{})
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
                if r.get('vlm'): done.add(r['slug'])
            except Exception: pass
    todo=[w for w in AW if w['slug'] not in done and os.path.exists(IMGDIR+w['slug']+'.jpg')]
    print(f"已完成 {len(done)} | 待跑 {len(todo)}",flush=True)
    ok=err=0
    with open(OUT,'a',encoding='utf-8') as f:
        for k,w in enumerate(todo):
            slug=w['slug']
            b64=base64.b64encode(open(IMGDIR+slug+'.jpg','rb').read()).decode()
            rec={"slug":slug,"title":w.get('title'),"artist":w.get('artist')}
            parsed=None
            for attempt in range(4):
                try:
                    txt,usage=call(b64); parsed=parse_json(txt)
                    if parsed: break
                    time.sleep(1)
                except Exception as e:
                    rec["error"]=repr(e)[:120]; time.sleep(2)
            if parsed:
                rec.update({"vlm":parsed}); rec.pop("error",None); ok+=1
            else:
                rec.setdefault("error","parse_fail"); err+=1
            f.write(json.dumps(rec,ensure_ascii=False)+"\n"); f.flush()
            if (k+1)%10==0: print(f"  {k+1}/{len(todo)} ok={ok} err={err}",flush=True)
            time.sleep(0.3)
    print(f"完成 ok={ok} err={err} | 总 {len(done)+ok+err}",flush=True)

if __name__=='__main__':
    main()
