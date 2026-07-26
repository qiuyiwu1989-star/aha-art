#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把三处分裂的艺术家关系收敛成一套规范边 kg_edges.json:
  源1 lore.teachers/students/peers(自由文本,每人一串名)
  源2 kg_artist_lineage.json(src/dst/rel,已 id 化)
  源3 kg_relations.json(8 种力 from/to/type,已 id 化,带 note/detail/conf)
统一格式 edge = {src,dst,src_name,dst_name,type,dir,conf,source,note?,year?,detail?}。
全部解析到 ARTIST.*;解析不到的保留 *_name + id=null(页面落检索)。去重(同 src·dst·type 合并,保信息最多的)。
另出 by_artist 索引(每位的 out/in 边)。幂等。
"""
import json, re, os, time
DEMO = "/home/ubuntu/users/qiuyiwu/aha-art-demo/data"
PUB = "/data/pub/p/aha/data"
LINEAGE_TYPES = {"师承", "同侪", "学生"}
FORCE_TYPES = {"反叛","复兴","综合","推演","跨文化","致敬","竞争","结社"}

def main():
    A = json.load(open(f"{DEMO}/kg_artists.json"))["artists"]
    cn2id = {}
    for id, v in A.items():
        if v.get("cn") and v["cn"] not in cn2id: cn2id[v["cn"]] = id
    def rid(nm):
        base = re.split(r'[（(]', str(nm))[0].strip()
        return cn2id.get(base), base

    edges = {}   # key=(src,dstkey,type) → edge dict
    def add(src, dst, src_name, dst_name, typ, dr, conf, source, **extra):
        dstkey = dst or ("name:" + (dst_name or ""))
        srckey = src or ("name:" + (src_name or ""))
        k = (srckey, dstkey, typ)
        e = edges.get(k)
        if not e:
            e = {"src": src, "dst": dst, "src_name": src_name, "dst_name": dst_name,
                 "type": typ, "dir": dr, "conf": conf, "source": source}
            edges[k] = e
        # 合并:补 note/detail/year/conf(考据 > 推断)
        for kk, vv in extra.items():
            if vv and not e.get(kk): e[kk] = vv
        if conf == "考据": e["conf"] = "考据"
        if source not in e["source"]: e["source"] += "+" + source

    # 源1:lore 自由文本(师承=老师→本人;学生=本人→学生;同侪=双向)
    for id, v in A.items():
        cn = v.get("cn")
        for t in (v.get("teachers") or []):
            tid, tn = rid(t); add(tid, id, t, cn, "师承", "→", "考据", "lore")
        for s in (v.get("students") or []):
            sid, sn = rid(s); add(id, sid, cn, s, "师承", "→", "考据", "lore")
        for p in (v.get("peers") or []):
            pid, pn = rid(p); add(id, pid, cn, p, "同侪", "↔", "推断", "lore")

    # 源2:kg_artist_lineage(已 id 化)
    for e in json.load(open(f"{DEMO}/kg_artist_lineage.json")).get("edges", []):
        s, d = e.get("src"), e.get("dst")
        typ = e.get("rel") or "师承"
        add(s, d, (A.get(s) or {}).get("cn"), (A.get(d) or {}).get("cn"), typ, "↔" if typ == "同侪" else "→", "考据", "lineage")

    # 源3:kg_relations(8 力,已 id 化)
    for e in json.load(open(f"{DEMO}/kg_relations.json")).get("edges", []):
        s, d = e.get("from"), e.get("to")
        add(s, d, e.get("from_cn") or (A.get(s) or {}).get("cn"), e.get("to_cn") or (A.get(d) or {}).get("cn"),
            e.get("type"), "↔" if e.get("bidir") else "→", e.get("conf") or "考据", "relations",
            note=e.get("note"), detail=e.get("detail"), year=e.get("year"))

    elist = list(edges.values())
    # by_artist 索引
    by = {}
    for e in elist:
        for end in ("src", "dst"):
            aid = e[end]
            if not aid: continue
            by.setdefault(aid, {"out": [], "in": []})
            (by[aid]["out"] if end == "src" else by[aid]["in"]).append(e)

    resolved = sum(1 for e in elist if e["src"] and e["dst"])
    dangling = sum(1 for e in elist if not e["dst"])
    out = {"meta": {"n": len(elist), "resolved": resolved, "dangling_dst": dangling,
                    "lineage_types": sorted(LINEAGE_TYPES), "force_types": sorted(FORCE_TYPES),
                    "built": time.strftime("%Y-%m-%d"),
                    "note": "三源(lore自由文本/kg_artist_lineage/kg_relations)收敛的规范关系边;dst=null 表示对象不在策展库(页面落检索)"},
           "edges": elist, "by_artist": by}
    for d in (DEMO, PUB):
        if os.path.isdir(d):
            json.dump(out, open(f"{d}/kg_edges.json", "w"), ensure_ascii=False, indent=1)
    print(f"✓ kg_edges.json:{len(elist)} 边(全解析 {resolved} · 对象悬空 {dangling})· 覆盖 {len(by)} 位艺术家")
    from collections import Counter
    print("  类型分布:", dict(Counter(e["type"] for e in elist)))

if __name__ == "__main__":
    main()
