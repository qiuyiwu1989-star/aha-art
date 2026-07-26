#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清洗作品标题:剥掉开头的【作者名/朝代时期前缀】(标题内的国家名是正当内容,保留)。
存 works.title_clean(仅当有变化),不动原 title。v_ledger 用 COALESCE(title_clean,cm.title,title)。可重跑。"""
import re, json, psycopg2
from psycopg2.extras import execute_values
d=json.load(open('/home/ubuntu/.aha_pg.json'))
con=psycopg2.connect(host=d['host'],port=d['port'],dbname=d['dbname'],user=d['user'],password=d['password']);cur=con.cursor()
# 列已存在就跳过 ALTER(避免与在线服务抢排他锁)
cur.execute("select 1 from information_schema.columns where table_name='works' and column_name='title_clean'")
if not cur.fetchone(): cur.execute("ALTER TABLE works ADD COLUMN title_clean text")
con.commit()

ERA=re.compile(r'^(现代|近现代|当代|古代|上古|远古|明代|清代|宋代|元代|唐代|汉代|明朝|清朝|宋朝|民国|文艺复兴|巴洛克|洛可可|印象派)[\s　]+')
SEP=' 　·•‧・-—:：，,'
def shortnames(cn,en):
    s=set()
    if cn:
        s.add(cn.strip())
        if '·' in cn: s.add(cn.split('·')[-1].strip())   # 末段简称(博尔迪尼)
        if '·' in cn: s.add(cn.split('·')[0].strip())    # 首段
    if en: s.add(en.strip())
    return {x for x in s if len(x)>=2}

# 取非dup作品的有效标题(优先簇合并标题)+艺术家名
cur.execute("""select w.work_id, coalesce(cm.title,w.title) t, a.name_cn, a.name_en
  from works w left join work_canonical_meta cm on cm.work_id=w.work_id
  left join artists a on a.artist_id=coalesce(a.canonical_artist_id,w.artist_id)
  where w.status<>'dup' and coalesce(cm.title,w.title) is not null""")
upd=[]; n=0; samp=[]
for wid,t,cn,en in cur.fetchall():
    orig=t; t=t.strip()
    changed=False
    m=ERA.match(t)
    if m: t=t[m.end():].lstrip(SEP); changed=True
    for nm in sorted(shortnames(cn,en),key=len,reverse=True):
        if t.startswith(nm) and len(t)>len(nm)+1 and t[len(nm)] in SEP:
            t=t[len(nm):].lstrip(SEP); changed=True; break
    if changed and t and t!=orig:
        upd.append((t,wid)); n+=1
        if len(samp)<10: samp.append((orig,t))
execute_values(cur,"update works set title_clean=v.t from (values %s) v(t,wid) where works.work_id=v.wid",upd,page_size=3000)
con.commit()
print(f"清洗标题 {n:,} 条(剥作者名/朝代前缀;国家名保留)")
for o,t in samp: print(f"  《{o}》→《{t}》")

# 注:v_ledger 视图的权威定义在 export_ledger.py(含 work_edit 编辑覆盖层);
# 这里只更新 title_clean 列,视图已 COALESCE 用它,不在此重建视图(避免冲掉编辑层)。
print("✓ title_clean 已更新(v_ledger 由 export_ledger.py 统一重建)")
