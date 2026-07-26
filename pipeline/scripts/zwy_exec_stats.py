import json,os,urllib.request,time,collections,datetime
KEY="sk-DYZfTj8acrqtOYmlMj4C8qSbgiAbcIHEuJCh17BbH2XQQlGJ";ID="67ee23b636ff1d9725e06306"
def get(path):
    req=urllib.request.Request(f"https://app.zaowuyun.com{path}",headers={"Authorization":f"Bearer {KEY}","x-monkeys-teamid":ID})
    return json.load(urllib.request.urlopen(req,timeout=40))
def post(path,data):
    req=urllib.request.Request(f"https://app.zaowuyun.com{path}",data=json.dumps(data).encode(),method="POST",headers={"Authorization":f"Bearer {KEY}","x-monkeys-teamid":ID,"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req,timeout=40))
wfs=[];p=1
while True:
    d=get(f"/api/workflow/metadata?page={p}&limit=50")["data"]
    if not d:break
    wfs+=d;p+=1
    if len(d)<50:break
byday=collections.Counter(); bystatus=collections.Counter(); total=0; t0=time.time()
for w in wfs:
    wid=w.get("workflowId") or w.get("id")
    page=1
    while True:
        try:
            r=post("/api/workflow/executions/search",{"workflowId":wid,"summaryOnly":True,"pagination":{"page":page,"limit":200},"orderBy":{"field":"startTime","order":"DESC"}})
        except Exception: break
        items=r["data"]["data"]; tot=r["data"]["total"]
        if not items: break
        for it in items:
            st=it.get("startTime")
            if st:
                d=datetime.datetime.fromtimestamp(st/1000).strftime("%Y-%m-%d"); byday[d]+=1
            bystatus[it.get("status","?")]+=1; total+=1
        if page*200>=tot: break
        page+=1
    if total and total%5000<200: print(f"  已扫 {total} 条 {total/(time.time()-t0):.0f}/s",flush=True)
json.dump({"byday":dict(byday),"bystatus":dict(bystatus),"total":total},open("/home/ubuntu/users/qiuyiwu/aha-art/pipeline/zwy_exec_stats.json","w"),ensure_ascii=False)
print(f"完成 总{total} 天数{len(byday)} 状态{dict(bystatus)} 用时{time.time()-t0:.0f}s")
