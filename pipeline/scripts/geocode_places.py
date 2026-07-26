#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给艺术家出生地批量地理编码(经纬度+国家),供来源地图。mimo 批量(它知道主要城市坐标)。
清洗:取 '[' 或 ',' 前主城名,剔 east/west 占位。存 place_geo 表。可重跑增量。
用法: python3 geocode_places.py [--limit N] [--batch 40]"""
import os, re, json, argparse, urllib.request, psycopg2
from psycopg2.extras import execute_values
def cfg(p): return json.load(open(os.path.expanduser(p)))
def mimo():
    m=cfg("~/.aha_mimo.json"); b=m["endpoint"].rstrip("/")
    if not b.endswith("/messages"): b+="/v1/messages"
    return b,m["key"],m["model"]
d=cfg("~/.aha_pg.json")
con=psycopg2.connect(host=d['host'],port=d['port'],dbname=d['dbname'],user=d['user'],password=d['password']);cur=con.cursor()
BASE,KEY,MODEL=mimo()
cur.execute("""CREATE TABLE IF NOT EXISTS place_geo(name text PRIMARY KEY, lat double precision, lng double precision, country text, geo_at timestamptz DEFAULT now())""")
con.commit()

def clean(r):
    r=re.split(r'[\[\(，,]', r)[0].strip()
    return r if (r and r not in ('east','west') and re.search(r'[一-鿿]', r)) else None

PROMPT="""给下列出生地(中文地名,多为欧洲/中国城市)返回经纬度和所属现代国家。
返回纯 JSON 数组,每项 {"name":原名,"lat":纬度,"lng":经度,"country":"中文国名"};
不确定的城市给所属国家首府或区域中心的近似坐标;长度与输入一致,顺序对应。
输入: %s"""
def geocode(names):
    body=json.dumps({"model":MODEL,"max_tokens":8000,"messages":[{"role":"user","content":[{"type":"text","text":PROMPT%json.dumps(names,ensure_ascii=False)}]}]}).encode()
    req=urllib.request.Request(BASE,data=body,method="POST",headers={"content-type":"application/json","x-api-key":KEY,"anthropic-version":"2023-06-01"})
    r=json.load(urllib.request.urlopen(req,timeout=300))
    txt="".join(b.get("text","") for b in r.get("content",[]) if b.get("type")=="text")
    m=re.search(r"\[.*\]",txt,re.S)
    return json.loads(m.group(0)) if m else None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--limit",type=int,default=500); ap.add_argument("--batch",type=int,default=40)
    a=ap.parse_args()
    cur.execute("""SELECT region, count(*) n FROM artist_assoc WHERE region IS NOT NULL AND region<>''
                   GROUP BY region ORDER BY 2 DESC""")
    seen=set(); todo=[]
    for r,n in cur.fetchall():
        c=clean(r)
        if c and c not in seen: seen.add(c); todo.append(c)
    cur.execute("SELECT name FROM place_geo"); have={x[0] for x in cur.fetchall()}
    todo=[t for t in todo if t not in have][:a.limit]
    print(f"待编码城市 {len(todo)}(覆盖艺术家最多的优先)",flush=True)
    n=0
    for i in range(0,len(todo),a.batch):
        chunk=todo[i:i+a.batch]
        try: g=geocode(chunk)
        except Exception as e: print(f"  批{i//a.batch+1} 异常 {str(e)[:50]}",flush=True); continue
        if not g: print(f"  批{i//a.batch+1} 失败",flush=True); continue
        rows=[(x.get("name"),x.get("lat"),x.get("lng"),x.get("country")) for x in g
              if x.get("name") and isinstance(x.get("lat"),(int,float)) and isinstance(x.get("lng"),(int,float))]
        if rows:
            execute_values(cur,"INSERT INTO place_geo(name,lat,lng,country) VALUES %s ON CONFLICT(name) DO NOTHING",rows)
            con.commit(); n+=len(rows)
        print(f"  批{i//a.batch+1}/{(len(todo)+a.batch-1)//a.batch}: +{len(rows)} (累计{n})",flush=True)
    print(f"\n完成 {n} 个城市坐标",flush=True)
    cur.execute("SELECT country,count(*) FROM place_geo GROUP BY 1 ORDER BY 2 DESC LIMIT 8")
    print("国家分布:",[(r[0],r[1]) for r in cur.fetchall()])

if __name__=="__main__": main()
