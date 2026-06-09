# -*- coding: utf-8 -*-
import json, urllib.request, sys
BASE="https://token-plan-cn.xiaomimimo.com/anthropic/v1/messages"
KEY="tp-cwxhnnn1oh0fzpm0h8uk8mey7342gfalfj3qev0p5nmpnbhv"
MODEL="mimo-v2.5"
def call(messages, max_tokens=200):
    body=json.dumps({"model":MODEL,"max_tokens":max_tokens,"messages":messages}).encode()
    req=urllib.request.Request(BASE,data=body,method="POST",headers={
        "content-type":"application/json","x-api-key":KEY,"anthropic-version":"2023-06-01"})
    with urllib.request.urlopen(req,timeout=120) as r:
        return json.loads(r.read())
import base64,os
def textof(out):
    return ' '.join(b.get('text','') for b in out.get('content',[]) if b.get('type')=='text').strip()
# 2) 视觉测试:一张真图
slug="m436965"
p="/data/pub/p/aha/img/%s.jpg"%slug
data=base64.b64encode(open(p,'rb').read()).decode()
msg=[{"role":"user","content":[
    {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":data}},
    {"type":"text","text":"这是一幅画。请用中文,一句话描述画面内容,再说它给人的主要情绪。"}]}]
try:
    out=call(msg,900)
    print("[视觉OK] stop=",out.get('stop_reason'))
    print("文本输出:",textof(out)[:600])
    print("usage:",out.get('usage'))
except Exception as e:
    print("[视觉失败]",repr(e)); import traceback; traceback.print_exc()
