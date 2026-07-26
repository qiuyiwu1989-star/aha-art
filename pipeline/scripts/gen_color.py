#!/usr/bin/env python3
"""给生成区 gen_file 已入库图算平均色+色相(COS ?imageAve,免下载)。
对称于 zwy_color.py(素材库),可重复跑补增量。色相分桶与素材库一致,
这样生成区也能用色彩筛选 / 主色搜同色。"""
import json,os,colorsys,urllib.request,urllib.parse,psycopg2,concurrent.futures as cf
c=json.load(open(os.path.expanduser('~/.aha_pg.json')));cc=json.load(open(os.path.expanduser('~/.aha_cos.json')))
HOST=f"aha-1254041526.cos.{cc['region']}.myqcloud.com"
cn=psycopg2.connect(**{k:c[k] for k in['host','port','dbname','user','password']});cn.autocommit=True;cu=cn.cursor()
def bucket(hx):
    r=int(hx[0:2],16)/255;g=int(hx[2:4],16)/255;b=int(hx[4:6],16)/255
    h,s,v=colorsys.rgb_to_hsv(r,g,b)
    if s<0.18 or v<0.12: return '中性'
    d=h*360
    return '红' if(d<20 or d>=330) else '橙' if d<45 else '黄' if d<70 else '绿' if d<160 else '青' if d<200 else '蓝' if d<260 else '紫'
def ave(k):
    try:
        u=f"https://{HOST}/"+urllib.parse.quote(k)+'?imageAve'
        hx=json.loads(urllib.request.urlopen(u,timeout=20).read())['RGB'][2:].rjust(6,'0');return k,hx,bucket(hx)
    except: return k,None,None
cu.execute("select cos_key from gen_file where source='zaowuyun_team' and role='output' and hue is null and cos_key is not null")
keys=[r[0] for r in cu.fetchall()];print("待算色彩",len(keys),flush=True)
n=0
with cf.ThreadPoolExecutor(max_workers=24) as ex:
    for k,hx,hue in ex.map(ave,keys):
        if hx: cu.execute("update gen_file set ave_rgb=%s,hue=%s where cos_key=%s",('#'+hx,hue,k));n+=1
        if n and n%2000==0: print("...已填",n,flush=True)
print("已填",n,flush=True)
