#!/usr/bin/env python3
"""给 dam_asset 缺主色的资产补 ave_rgb+hue(COS ?imageAve 服务端算,免下载,桶无关)。
覆盖艺术库等 cos 库,让色彩检索/找同色全库可用。增量:只补 hue 为空的。"""
import json, os, colorsys, urllib.request, urllib.parse, ssl, psycopg2, concurrent.futures as cf
c = json.load(open(os.path.expanduser('~/.aha_pg.json')))
cc = json.load(open(os.path.expanduser('~/.aha_cos.json')))
REGION = cc['region']
_SSL = ssl.create_default_context(); _SSL.check_hostname = False; _SSL.verify_mode = ssl.CERT_NONE
cn = psycopg2.connect(**{k: c[k] for k in ['host','port','dbname','user','password']}); cn.autocommit = True; cu = cn.cursor()

def bucket_hue(hx):
    r, g, b = int(hx[0:2],16)/255, int(hx[2:4],16)/255, int(hx[4:6],16)/255
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.18 or v < 0.12: return '中性'
    d = h*360
    return '红' if (d < 20 or d >= 330) else '橙' if d < 45 else '黄' if d < 70 else '绿' if d < 160 else '青' if d < 200 else '蓝' if d < 260 else '紫'

def ave(row):
    aid, bucket, key = row
    try:
        host = f"{bucket}.cos.{REGION}.myqcloud.com"
        u = f"https://{host}/" + urllib.parse.quote(key, safe='/') + '?imageAve'
        hx = json.loads(urllib.request.urlopen(u, timeout=20, context=_SSL).read())['RGB'][2:].rjust(6, '0')
        return aid, '#' + hx, bucket_hue(hx)
    except Exception:
        return aid, None, None

cu.execute("SELECT asset_id, bucket, cos_key FROM dam_asset WHERE status='active' AND hue IS NULL AND cos_key IS NOT NULL")
rows = cu.fetchall(); print("待补主色", len(rows), flush=True)
n = 0
with cf.ThreadPoolExecutor(max_workers=24) as ex:
    for aid, hx, hue in ex.map(ave, rows):
        if hx:
            cu.execute("UPDATE dam_asset SET ave_rgb=%s, hue=%s WHERE asset_id=%s", (hx, hue, aid)); n += 1
        if n and n % 5000 == 0: print("...已补", n, flush=True)
print("完成,补了", n, flush=True)
