#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给全量艺术家推断 east/west(展出'分东西'维度)。语料~99%西方,故高精度识别东方、其余默认西方。
东方判据(任一):curated=east / 出生地在东方城市 / school含东方画种 / name_cn纯汉字无·且无西文名。"""
import re, json, psycopg2
from psycopg2.extras import execute_values
d=json.load(open('/home/ubuntu/.aha_pg.json'))
con=psycopg2.connect(host=d['host'],port=d['port'],dbname=d['dbname'],user=d['user'],password=d['password']);cur=con.cursor()
# 列已存在就跳过 ALTER(避免与在线服务抢排他锁)
cur.execute("select 1 from information_schema.columns where table_name='artists' and column_name='east_west'")
if not cur.fetchone(): cur.execute("ALTER TABLE artists ADD COLUMN east_west text")
con.commit()

EAST_PLACE=set("北京 上海 杭州 南京 苏州 广州 成都 西安 天津 重庆 武汉 长沙 香港 台北 台湾 沈阳 大连 青岛 宁波 绍兴 无锡 扬州 镇江 嘉兴 湖州 常州 福州 厦门 济南 郑州 洛阳 昆明 贵阳 兰州 银川 太原 石家庄 哈尔滨 长春 南昌 合肥 南宁 海口 拉萨 乌鲁木齐 呼和浩特 东京 京都 大阪 名古屋 横滨 神户 奈良 首尔 汉城 釜山 平壤 河内 曼谷 新德里 孟买 加尔各答 德黑兰".split())
EAST_KW=re.compile(r'中国|中華|日本|朝鲜|朝鮮|韩国|韓國|印度|越南|泰国|波斯|蒙古|江苏|浙江|湖南|湖北|广东|四川|山东|河南|河北|安徽|福建|江西|陕西|山西|辽宁|吉林|黑龙江|云南|贵州|甘肃|台|藏')
EAST_SCHOOL=re.compile(r'浮世绘|水墨|山水|中国画|國畫|国画|工笔|写意|花鸟|书法|院体|文人画|岭南|海派|东方')
HAN=re.compile(r'^[一-鿿]{2,5}$')   # 纯汉字、无·、2-5字

cur.execute("select canon_id,region from artists_canon")
canon_ew={cid:reg for cid,reg in cur.fetchall() if reg in ('east','west')}

cur.execute("select artist_id,name_cn,name_en,region,aha_kg_id from artists")
rows=cur.fetchall()
# 需要 school:从该艺术家名下作品取一个非空 school
cur.execute("select artist_id, max(school) from works where school is not null group by artist_id")
asch=dict(cur.fetchall())

def is_east(aid,cn,en,region,kg):
    if kg and canon_ew.get(kg)=='east': return True
    if kg and canon_ew.get(kg)=='west': return False
    if region and (region in EAST_PLACE or EAST_KW.search(region)): return True
    sc=asch.get(aid) or ''
    if EAST_SCHOOL.search(sc): return True
    if cn and '·' not in cn and HAN.match(cn) and not en: return True   # 纯汉字名+无西文名=东方画家
    return None  # 未命中东方
upd=[]
for aid,cn,en,region,kg in rows:
    e=is_east(aid,cn,en,region,kg)
    upd.append(('west' if e is False or e is None else 'east', aid))
execute_values(cur,"update artists set east_west=v.ew from (values %s) v(ew,aid) where artists.artist_id=v.aid",upd,page_size=3000)
con.commit()
cur.execute("select east_west,count(*) from artists group by 1")
print("艺术家 east/west:",{r[0]:r[1] for r in cur.fetchall()})
# 落到作品层(经 v_ledger 的 east_west 已读 curated;这里给个作品级统计)
cur.execute("""select coalesce(a2.east_west,'?') ew,count(*) from works w
  left join artists a on a.artist_id=w.artist_id
  left join artists a2 on a2.artist_id=coalesce(a.canonical_artist_id,w.artist_id)
  where w.status<>'dup' group by 1 order by 2 desc""")
print("作品层(非dup) east/west:",{r[0]:r[1] for r in cur.fetchall()})
print("东方样例:")
cur.execute("select name_cn,name_en from artists where east_west='east' and name_cn is not null order by random() limit 8")
print("  ",[r[0] for r in cur.fetchall()])
