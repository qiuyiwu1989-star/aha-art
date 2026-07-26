#!/usr/bin/env python3
"""第2步·东方归位:把 108 个 eastern_lineage 节点从 canonical='other' 迁到 style_canon 的东方细码。
- style_canon 加 parent_id(自指),建 13 个东方细码:中国本土 11 类 parent=22(中国画),日本/朝鲜独立。
- style_nodes 加 canon_id(int FK style_canon),按 eastern_lineage 填这 108 个(西方/无lineage节点不动,canon_id 留空)。
- 顺手修「岭南画派」误标 e_japan→e_regional_school。
全程不动:西方202节点的旧 canonical、works、style_map、归一台。可回滚(见文件末注释)。
"""
import json, psycopg2
cfg=json.load(open('/home/ubuntu/.aha_pg.json'))
conn=psycopg2.connect(host=cfg['host'],port=cfg['port'],dbname=cfg['dbname'],user=cfg['user'],password=cfg['password'])
cur=conn.cursor()

# eastern_lineage -> (canon_id, 中文名, 英文名, parent_id)。中国本土 parent=22(中国画);日本/朝鲜 parent=None。
EAST = [
 ('e_literati_ink',       23,'文人画',     'Literati Painting',     22),
 ('e_landscape',          24,'山水画',     'Shanshui Landscape',    22),
 ('e_regional_school',    25,'地域画派',   'Regional Schools',      22),
 ('e_religious',          26,'宗教绘画',   'Religious Painting',    22),
 ('e_figure',             27,'人物画',     'Figure Painting',       22),
 ('e_prehistoric_object', 28,'史前与器物', 'Prehistoric & Artifact',22),
 ('e_gongbi_color',       29,'工笔重彩',   'Gongbi & Heavy Color',  22),
 ('e_folk',               30,'民间美术',   'Folk Art',              22),
 ('e_tomb_silk',          31,'墓室帛画',   'Tomb & Silk Painting',  22),
 ('e_bird_flower',        32,'花鸟画',     'Bird-and-Flower',       22),
 ('e_contemporary_ink',   33,'当代水墨',   'Contemporary Ink',      22),
 ('e_japan',              34,'日本绘画',   'Japanese Painting',     None),
 ('e_korea',              35,'朝鲜绘画',   'Korean Painting',       None),
]
lineage2canon={l:cid for l,cid,_,_,_ in EAST}

try:
    # 1) style_canon 加 parent_id
    cur.execute("ALTER TABLE style_canon ADD COLUMN IF NOT EXISTS parent_id integer REFERENCES style_canon(canon_id)")
    # 2) 插 13 东方细码(幂等)
    for l,cid,zh,en,pid in EAST:
        cur.execute("""INSERT INTO style_canon(canon_id,name_cn,name_en,sort,parent_id)
                       VALUES(%s,%s,%s,%s,%s)
                       ON CONFLICT(canon_id) DO UPDATE SET name_cn=EXCLUDED.name_cn,
                         name_en=EXCLUDED.name_en, parent_id=EXCLUDED.parent_id""",
                    (cid,zh,en,cid,pid))
    # 3) style_nodes 加 canon_id(int FK)
    cur.execute("ALTER TABLE style_nodes ADD COLUMN IF NOT EXISTS canon_id integer REFERENCES style_canon(canon_id)")
    # 4) 修「岭南画派」误标:e_japan -> e_regional_school
    cur.execute("UPDATE style_nodes SET eastern_lineage='e_regional_school' WHERE cn='岭南画派风格' AND eastern_lineage='e_japan'")
    fixed=cur.rowcount
    # 5) 按 eastern_lineage 填 canon_id(只动 region=east 且 canonical='other' 的那批=有lineage的108个)
    filled={}
    for l,cid in lineage2canon.items():
        cur.execute("""UPDATE style_nodes SET canon_id=%s
                       WHERE region='east' AND canonical='other' AND eastern_lineage=%s""",(cid,l))
        if cur.rowcount: filled[l]=cur.rowcount
    conn.commit()

    # 验证
    cur.execute("SELECT count(*) FROM style_nodes WHERE canon_id IS NOT NULL")
    tot=cur.fetchone()[0]
    cur.execute("""SELECT count(*) FROM style_nodes WHERE region='east' AND canonical='other' AND eastern_lineage IS NOT NULL AND canon_id IS NULL""")
    leftover=cur.fetchone()[0]
    print(f"✓ 岭南画派修正: {fixed} 条")
    print(f"✓ 填 canon_id 节点数: {tot}  (应=108)")
    print(f"✓ 仍漏填的有lineage东方节点(应=0): {leftover}")
    print("  各细码落点:")
    cur.execute("""SELECT sc.canon_id, sc.name_cn, sc.parent_id, count(sn.style_id)
                   FROM style_canon sc LEFT JOIN style_nodes sn ON sn.canon_id=sc.canon_id
                   WHERE sc.canon_id BETWEEN 23 AND 35 GROUP BY 1,2,3 ORDER BY 1""")
    for cid,zh,pid,n in cur.fetchall():
        print(f"    {cid} {zh}{'(中国画下)' if pid==22 else '(独立)'}: {n} 节点")
except Exception as e:
    conn.rollback(); print("✗ 回滚:", e); raise
finally:
    conn.close()

# ===== 回滚 =====
# ALTER TABLE style_nodes DROP COLUMN canon_id;
# DELETE FROM style_canon WHERE canon_id BETWEEN 23 AND 35;
# ALTER TABLE style_canon DROP COLUMN parent_id;
# (岭南画派 eastern_lineage 改回 e_japan 如需)
