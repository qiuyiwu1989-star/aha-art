#!/usr/bin/env python3
"""统计造物云「创意设计」全部工作流执行(生成)记录的每日数量。"""
import json, os, urllib.request, time, collections, datetime, threading
from concurrent.futures import ThreadPoolExecutor
H = {"Authorization": "Bearer sk-DYZfTj8acrqtOYmlMj4C8qSbgiAbcIHEuJCh17BbH2XQQlGJ",
     "x-monkeys-teamid": "67ee23b636ff1d9725e06306", "Content-Type": "application/json"}
def get(p): return json.load(urllib.request.urlopen(urllib.request.Request("https://app.zaowuyun.com"+p, headers=H), timeout=60))
def post(d): return json.load(urllib.request.urlopen(urllib.request.Request("https://app.zaowuyun.com/api/workflow/executions/search", data=json.dumps(d).encode(), method="POST", headers=H), timeout=90))

wfs = []; p = 1
while True:
    d = get(f"/api/workflow/metadata?page={p}&limit=50")["data"]
    if not d: break
    wfs += d; p += 1
    if len(d) < 50: break
print(f"工作流 {len(wfs)} 个", flush=True)

byday = collections.Counter(); bystatus = collections.Counter(); lock = threading.Lock(); tot = [0]; t0 = time.time()
def scan(w):
    wid = w.get("workflowId") or w.get("id"); page = 1; loc = collections.Counter(); ls = collections.Counter(); n = 0
    while True:
        try:
            r = post({"workflowId": wid, "summaryOnly": True, "pagination": {"page": page, "limit": 300}, "orderBy": {"field": "startTime", "order": "DESC"}})
        except Exception as e:
            print(f"  ERR p{page}: {str(e)[:40]}", flush=True); break
        items = r["data"]["data"]; T = r["data"]["total"]
        if not items: break
        for it in items:
            st = it.get("startTime")
            if st: loc[datetime.datetime.fromtimestamp(st/1000).strftime("%Y-%m-%d")] += 1
            ls[it.get("status", "?")] += 1; n += 1
        if page*300 >= T: break
        page += 1
    with lock:
        byday.update(loc); bystatus.update(ls); tot[0] += n
        if n: print(f"  +{n} 累计{tot[0]} ({tot[0]/(time.time()-t0):.0f}/s)", flush=True)

with ThreadPoolExecutor(max_workers=12) as ex:
    list(ex.map(scan, wfs))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "zwy_exec_stats.json")
json.dump({"byday": dict(byday), "bystatus": dict(bystatus), "total": tot[0]}, open(out, "w"), ensure_ascii=False)
print(f">>> 完成 总 {tot[0]} 天数 {len(byday)} 用时 {time.time()-t0:.0f}s", flush=True)
