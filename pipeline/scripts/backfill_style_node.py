#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 works 的原始 school 串「白嫖」细分到 202 富节点 → works.style_node_id(STYLE.*)。
加法式 + 幂等:加列(NULL默认)+ 按 school 批量回填;可反复跑,新灌入的作品再跑一次即补上。
零 VLM,纯规则——只对原始串本身就比32码细的(北方/早期文艺复兴、社会现实、超现实…)生效;
其余留 NULL(仍可用 works.style_id 走 canonical 组粒度)。

⚠ 并发须知:works 表正被其它会话写入。本脚本对热表只做 ADD COLUMN(快/非阻塞)+ UPDATE...WHERE school=X
(MVCC 下不阻塞 INSERT),安全。但请在协调窗口运行,跑完告知。

用法: python3 backfill_style_node.py --check   # 只看覆盖,不写库
      python3 backfill_style_node.py           # 加列+回填
"""
import json, os, re, sys, argparse
from collections import defaultdict
from style_norm import to_style_id

NODES=[n for n in json.load(open('/data/pub/p/aha/data/kg_style.json'))['nodes']]
SYN={'高文艺复兴':['盛期','文艺复兴盛期'],'早期文艺复兴':['文艺复兴早期','早期文艺复兴','early renaissance','15世纪'],
 '晚期文艺复兴':['样式主义','矫饰','late renaissance','意大利晚期'],'北方文艺复兴':['尼德兰','弗拉芒','flemish','北方','northern'],
 '社会现实主义':['社会现实','社会主义现实'],'照相写实主义':['照相写实','photoreal'],'超写实主义':['超写实','hyperreal'],
 '魔幻现实主义':['魔幻现实','幻想现实','magic realism'],'点彩派':['点彩','分隔','pointil','divisionism'],
 '分析立体主义':['分析立体','analytic'],'综合立体主义':['综合立体','synthetic cub'],'色域绘画':['色域','color field'],
 '动作绘画':['动作','action paint'],'新即物主义':['新即物','new objectiv','neue sachl']}
def keys(n):
    base=re.sub(r'(风格|画风|主义)$','',n['cn'])
    return {k.lower() for k in set([n['cn'],base]+(n.get('aka') or [])+SYN.get(n['cn'],[])) if k and len(k)>=2}
bycanon=defaultdict(list)
for n in NODES:
    if n.get('canonical'): bycanon[n['canonical']].append(n)
def fine_node(school):
    c=to_style_id(school)
    if not c or c=='other': return None
    s=school.lower(); best=None; bl=-1
    for n in bycanon.get(c,[]):
        for k in keys(n):
            if k in s and len(k)>bl: best=n['id']; bl=len(k)
    return best

def pg():
    import psycopg2
    d=json.load(open(os.path.expanduser("~/.aha_pg.json")))
    return psycopg2.connect(host=d["host"],port=d["port"],dbname=d["dbname"],user=d["user"],password=d["password"])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--check",action="store_true"); a=ap.parse_args()
    cn=pg(); cur=cn.cursor()
    cur.execute("SELECT school,count(*) FROM works WHERE school IS NOT NULL AND school<>'' GROUP BY school")
    rows=cur.fetchall(); total=sum(n for _,n in rows)
    mapping={s:fine_node(s) for s,_ in rows}; mapping={s:v for s,v in mapping.items() if v}
    fine=sum(n for s,n in rows if s in mapping)
    print(f"全库挂风格 {total} 件;可白嫖细分 {fine} 件 ({fine*100//total}%),命中 {len(mapping)} 个原始串")
    if a.check: cn.close(); return
    cur.execute("ALTER TABLE works ADD COLUMN IF NOT EXISTS style_node_id text")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_works_style_node ON works(style_node_id)")
    upd=0
    for school,nid in mapping.items():
        cur.execute("UPDATE works SET style_node_id=%s WHERE school=%s AND style_node_id IS DISTINCT FROM %s",(nid,school,nid))
        upd+=cur.rowcount
    cn.commit()
    print(f"✓ works.style_node_id 回填/更新 {upd} 行(幂等,可重跑补新作品)")
    cn.close()

if __name__=="__main__": main()
