#!/usr/bin/env python3
"""从国画 cos_key 路径抽 朝代/画家 → dam_tag_item(source='path'),免 VLM,立即覆盖全部。
路径形如 artworks/国画浏览版/<朝代>/<画家或册名>/... 或 .../<朝代>/<朝代-画家-册名>/...
幂等:ON CONFLICT DO NOTHING。"""
import json, os, re, psycopg2
def pg():
    d=json.load(open(os.path.expanduser("~/.aha_pg.json")))
    return psycopg2.connect(host=d["host"],port=d["port"],dbname=d["dbname"],user=d["user"],password=d["password"])

DYN = {"先秦","秦","汉","魏","晋","隋","唐","五代","宋","辽","金","元","明","清","近代","现代","民国"}

def parse(cos_key):
    parts = (cos_key or "").split("/")
    if len(parts) < 4 or "国画" not in (parts[1] if len(parts)>1 else ""):
        return None, None
    dyn = parts[2] if parts[2] in DYN else None
    artist = None
    seg = parts[3]
    if "-" in seg:
        # 朝代-画家-册名...  取第二段作画家
        bits = seg.split("-")
        if len(bits) >= 2 and 1 <= len(bits[1]) <= 5:
            artist = bits[1]
    elif 1 <= len(seg) <= 5 and not re.search(r"\d", seg):
        artist = seg   # 干净的画家名文件夹
    return dyn, artist

def main():
    cn=pg(); cn.autocommit=True; c=cn.cursor()
    c.execute("SELECT asset_id, ext_id, cos_key FROM dam_asset WHERE lib='guohua' AND status='active'")
    rows=c.fetchall(); n_d=n_a=0
    for aid, ext, key in rows:
        item = ext or ("a"+str(aid))
        dyn, artist = parse(key)
        if dyn:
            c.execute("INSERT INTO dam_tag_item(lib,item_id,tag,facet,source,conf) VALUES('guohua',%s,%s,'朝代','path',NULL) ON CONFLICT DO NOTHING",(item,dyn)); n_d+=c.rowcount
        if artist:
            c.execute("INSERT INTO dam_tag_item(lib,item_id,tag,facet,source,conf) VALUES('guohua',%s,%s,'画家','path',NULL) ON CONFLICT DO NOTHING",(item,artist)); n_a+=c.rowcount
    print(f"国画 {len(rows)} 张:新增 朝代标签 {n_d}, 画家标签 {n_a}")
    # 画家分布
    c.execute("SELECT tag,count(*) FROM dam_tag_item WHERE lib='guohua' AND facet='画家' GROUP BY 1 ORDER BY 2 DESC LIMIT 10")
    print("画家 top:", c.fetchall())
    c.close(); cn.close()

if __name__=="__main__": main()
