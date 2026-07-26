#!/usr/bin/env python3
"""第3步a·西方对齐:把 ~86 个西方 style_nodes 也挂到主干 style_canon(填 canon_id)。
- 补 10 个西方大类码进 style_canon(主干缺的);4 个译名差异映射到现有码。
- 按节点 canonical(slug) 填 canon_id。东方/已填的不动。
可回滚(见末尾)。
"""
import json, psycopg2
cfg=json.load(open('/home/ubuntu/.aha_pg.json'))
conn=psycopg2.connect(host=cfg['host'],port=cfg['port'],dbname=cfg['dbname'],user=cfg['user'],password=cfg['password'])
cur=conn.cursor()

# 要新建的 10 个西方大类码(canon_id 36-45, parent=None 即顶层大类)
NEW = [
 (36,'抽象艺术',  'Abstract Art'),
 (37,'中世纪艺术','Medieval Art'),
 (38,'古典主义',  'Classicism'),
 (39,'达达主义',  'Dada'),
 (40,'波普艺术',  'Pop Art'),
 (41,'新艺术运动','Art Nouveau'),
 (42,'装饰艺术',  'Art Deco'),
 (43,'未来主义',  'Futurism'),
 (44,'野兽派',    'Fauvism'),
 (45,'东方主义',  'Orientalism'),
]
# 西方 slug -> canon_id(16 同名 + 4 译名映射到现有 + 10 新建 + other→0)
SLUG2CANON = {
 'renaissance':1,'mannerism':2,'baroque':3,'rococo':4,'neoclassicism':5,'romanticism':6,
 'realism':7,'pre_raphaelite':8,'impressionism':9,'neo_impressionism':10,'post_impressionism':11,
 'symbolism':12,'ecole_de_paris':13,'expressionism':14,'cubism':15,'surrealism':16,
 'abstract_expressionism':17,'naive_art':18,'contemporary':20,            # 译名:现当代→当代艺术20
 'abstract_art':36,'medieval':37,'classicism':38,'dada':39,'pop_art':40,
 'art_nouveau':41,'art_deco':42,'futurism':43,'fauvism':44,'orientalism':45,'other':0,
}
try:
    for cid,zh,en in NEW:
        cur.execute("""INSERT INTO style_canon(canon_id,name_cn,name_en,sort,parent_id)
                       VALUES(%s,%s,%s,%s,NULL)
                       ON CONFLICT(canon_id) DO UPDATE SET name_cn=EXCLUDED.name_cn,name_en=EXCLUDED.name_en""",
                    (cid,zh,en,cid))
    filled=0; skip=[]
    for slug,cid in SLUG2CANON.items():
        cur.execute("""UPDATE style_nodes SET canon_id=%s
                       WHERE region<>'east' AND canonical=%s AND canon_id IS NULL""",(cid,slug))
        filled+=cur.rowcount
    conn.commit()

    cur.execute("SELECT count(*) FROM style_nodes WHERE region<>'east' AND canon_id IS NULL AND canonical IS NOT NULL")
    leftover=cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM style_nodes WHERE canon_id IS NOT NULL")
    tot=cur.fetchone()[0]
    print(f"✓ 西方填 canon_id: {filled} 个  | 仍漏(应0): {leftover}")
    print(f"✓ 全库已挂主干节点总数: {tot} / 204")
    cur.execute("SELECT count(*) FROM style_nodes WHERE canon_id IS NULL")
    print(f"  仍未挂主干(无canonical的壳等): {cur.fetchone()[0]}")
except Exception as e:
    conn.rollback(); print("✗ 回滚:",e); raise
finally:
    conn.close()
# 回滚: UPDATE style_nodes SET canon_id=NULL WHERE region<>'east';
#       DELETE FROM style_canon WHERE canon_id BETWEEN 36 AND 45;
