#!/usr/bin/env python3
"""意境(mood)标签归一:把 VLM 生成的自由组合(苍劲古朴/古朴苍劲/古朴庄重…)拆映射到规范词表。
命中的规范词各成一个标签(可多个),没命中的保留原样。存量一次性清理;vlm_art 新标注同样调 canon_moods。"""
import json, os, psycopg2

# 规范意境词表(书画 + 设计/网页气质)
CANON = ["空灵","苍劲","清雅","萧疏","古朴","雄浑","淡雅","秀润","静谧","幽远",
         "恬淡","雅致","豪迈","富贵","庄重","清幽","沉郁","明快","温润","灵动",
         "宁静","悠远","雄奇","飘逸","肃穆","优雅","神秘","梦幻",
         "高级","活力","专业","温暖","未来感","科技感","复古","时尚","热烈","清新","质朴"]

def canon_moods(tag):
    """返回该 mood 命中的规范词(可能多个);没命中返回 [原tag]。"""
    tag = (tag or "").strip()
    found = [c for c in CANON if c in tag and c != tag]  # 作为子串命中的规范词
    if tag in CANON: return [tag]
    return found if found else [tag]

def main():
    d=json.load(open(os.path.expanduser("~/.aha_pg.json")))
    cn=psycopg2.connect(host=d["host"],port=d["port"],dbname=d["dbname"],user=d["user"],password=d["password"]);cn.autocommit=True;c=cn.cursor()
    c.execute("SELECT DISTINCT tag FROM dam_tag_item WHERE facet='意境'")
    tags=[r[0] for r in c.fetchall()]
    changed=0
    for tag in tags:
        canon=canon_moods(tag)
        if canon==[tag]: continue
        for ct in canon:
            c.execute("""INSERT INTO dam_tag_item(lib,item_id,tag,facet,source,conf)
                         SELECT lib,item_id,%s,'意境',source,conf FROM dam_tag_item WHERE facet='意境' AND tag=%s
                         ON CONFLICT DO NOTHING""",(ct,tag))
        c.execute("DELETE FROM dam_tag_item WHERE facet='意境' AND tag=%s",(tag,))
        changed+=1
    c.execute("SELECT count(distinct tag) FROM dam_tag_item WHERE facet='意境'")
    print(f"意境归一:处理 {changed} 种非规范词 → 现规范词 {c.fetchone()[0]} 种")
    c.execute("SELECT tag,count(*) FROM dam_tag_item WHERE facet='意境' GROUP BY 1 ORDER BY 2 DESC LIMIT 12")
    print("意境 top:",[(t,n) for t,n in c.fetchall()])
    c.close();cn.close()

if __name__=="__main__": main()
