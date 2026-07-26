#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""流派归一:把 school 的 164 个中英混杂取值映射到一套规范流派词表。
建 style_canon(规范词表)+ style_map(原值→规范,规则自动填,后台可改);v_ledger 加 style_canon 列。可重跑。"""
import json, psycopg2
from psycopg2.extras import execute_values
d=json.load(open('/home/ubuntu/.aha_pg.json'))
con=psycopg2.connect(host=d['host'],port=d['port'],dbname=d['dbname'],user=d['user'],password=d['password']);cur=con.cursor()

# 规范流派词表(id, 中文, 英文, 排序≈艺术史时序)
CANON=[(1,'文艺复兴','Renaissance'),(2,'样式主义','Mannerism'),(3,'巴洛克','Baroque'),(4,'洛可可','Rococo'),
 (5,'新古典主义','Neoclassicism'),(6,'浪漫主义','Romanticism'),(7,'现实主义','Realism'),
 (8,'拉斐尔前派','Pre-Raphaelite'),(9,'印象派','Impressionism'),(10,'新印象派','Neo-Impressionism'),
 (11,'后印象派','Post-Impressionism'),(12,'象征主义','Symbolism'),(13,'巴黎画派','École de Paris'),
 (14,'表现主义','Expressionism'),(15,'立体主义','Cubism'),(16,'超现实主义','Surrealism'),
 (17,'抽象表现主义','Abstract Expressionism'),(18,'朴素艺术','Naïve Art'),(19,'现代主义','Modernism'),
 (20,'当代艺术','Contemporary'),(21,'浮世绘','Ukiyo-e'),(22,'中国画','Chinese Painting'),(0,'其他/未分类','Other')]
cur.execute("create table if not exists style_canon(canon_id int primary key, name_cn text, name_en text, sort int)")
execute_values(cur,"insert into style_canon(canon_id,name_cn,name_en,sort) values %s on conflict(canon_id) do update set name_cn=excluded.name_cn,name_en=excluded.name_en",
  [(i,cn,en,idx) for idx,(i,cn,en) in enumerate(CANON)])
cur.execute("create table if not exists style_map(raw text primary key, canon_id int, auto boolean default true)")
con.commit()

# 规则(按特异性排序;先匹配长/特殊的)
RULES=[
 ('abstract_expressionism',17),('抽象表现',17),
 ('post_impressionism',11),('后印象',11),
 ('neo_impressionism',10),('新印象',10),
 ('impressionism',9),('印象派',9),('印象主义',9),
 ('neoclassicism',5),('新古典',5),
 ('pre_raphaelite',8),('拉斐尔前',8),
 ('ecole_de_paris',13),('巴黎画派',13),('巴黎高等',13),
 ('naive_art_primitivism',18),('朴素艺术',18),('原始主义',18),
 ('expressionism',14),('表现主义',14),
 ('surrealism',16),('超现实',16),
 ('symbolism',12),('象征',12),
 ('romanticism',6),('浪漫',6),
 ('realism',7),('现实主义',7),('写实',7),
 ('baroque',3),('巴洛克',3),
 ('rococo',4),('洛可可',4),
 ('mannerism',2),('样式主义',2),
 ('cubism',15),('立体',15),
 ('renaissance',1),('文艺复兴',1),
 ('当代',20),('contemporary',20),('20世纪',19),('现代主义',19),('两次世界大战',19),('战后',19),('modernism',19),
 ('浮世绘',21),('ukiyo',21),('日本水墨',21),
 ('中国画',22),('国画',22),('水墨',22),('山水',22),('花鸟',22),('工笔',22),('写意',22),('近现代',22),
 ('古典主义',5),('古典',5),
]
def match(raw):
    s=raw.lower()
    for kw,cid in RULES:
        if kw.lower() in s: return cid
    return 0

cur.execute("select distinct school from works where school is not null and school<>''")
raws=[r[0] for r in cur.fetchall()]
rows=[]
for raw in raws:
    rows.append((raw, match(raw)))
# 只插新的/保留已人工改的(auto=false不覆盖)
execute_values(cur,"insert into style_map(raw,canon_id,auto) values %s on conflict(raw) do update set canon_id=excluded.canon_id where style_map.auto=true",
  [(r,c,True) for r,c in rows],page_size=1000)
con.commit()

# 重建 v_ledger 加 style_canon(权威定义在 export_ledger,这里只做统计;视图列在 export_ledger 加)
n_unmapped=sum(1 for _,c in rows if c==0)
print(f"流派归一: {len(raws)} 个原值 → 规范词表 {len(CANON)} 类;未匹配(归其他) {n_unmapped} 个")
cur.execute("""select sc.name_cn, count(*) n from works w join style_map sm on sm.raw=w.school
  join style_canon sc on sc.canon_id=sm.canon_id where w.status<>'dup' group by sc.name_cn,sc.sort order by min(sc.sort)""")
print("规范流派分布(作品数):")
for r in cur.fetchall(): print(f"  {r[1]:>7,}  {r[0]}")
cur.execute("select raw,canon_id from style_map where canon_id=0 limit 12")
print("归'其他'的原值(待人工归类):",[r[0] for r in cur.fetchall()])
