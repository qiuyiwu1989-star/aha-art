#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 mu_user 的 IP 反查国家/城市(ip-api.com 免费批量,45次/分)。只查未解析的公网IP。可重跑/定时。"""
import json, ipaddress, urllib.request, psycopg2
d=json.load(open('/home/ubuntu/.aha_pg.json'))
con=psycopg2.connect(host=d['host'],port=d['port'],dbname=d['dbname'],user=d['user'],password=d['password']);cur=con.cursor()

cur.execute("""SELECT DISTINCT ip FROM mu_user
  WHERE ip IS NOT NULL AND ip_geo_at IS NULL""")
ips=[r[0] for r in cur.fetchall()]
def is_public(ip):
    try: return not ipaddress.ip_address(ip).is_private
    except Exception: return False
ips=[ip for ip in ips if is_public(ip)]
if not ips:
    print("无待解析的公网IP"); raise SystemExit
print(f"待解析 IP {len(ips)} 个")

def batch(chunk):
    body=json.dumps([{"query":ip,"fields":"query,status,country,countryCode,city,regionName,isp"} for ip in chunk]).encode()
    req=urllib.request.Request("http://ip-api.com/batch", data=body, headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req, timeout=20))

n=0
for i in range(0,len(ips),100):
    chunk=ips[i:i+100]
    try: res=batch(chunk)
    except Exception as e: print("批次失败:",str(e)[:80]); break
    for ip,r in zip(chunk,res):
        if isinstance(r,dict) and r.get("status")=="success":
            cur.execute("UPDATE mu_user SET ip_country=%s, ip_city=%s, ip_geo_at=now() WHERE ip=%s",
                        (r.get("country"), r.get("city") or r.get("regionName"), ip)); n+=cur.rowcount
        else:
            cur.execute("UPDATE mu_user SET ip_geo_at=now() WHERE ip=%s",(ip,))
    con.commit()
print(f"解析完成,更新 {n} 个用户的地理")
cur.execute("SELECT ip_country,count(*) FROM mu_user WHERE ip_country IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 8")
print("地区分布:",[(r[0],r[1]) for r in cur.fetchall()])
