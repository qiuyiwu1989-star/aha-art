#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""投影层:活库(Postgres) → 知识结构页要的 JSON 切片(web/data/live/*)。

原则:旧 demo JSON 不动;活数据写到 web/data/live/(新目录);各 -live 页读这里。
幂等可重跑,过闸推进后重跑即刷新。作用域默认 kept(核心资产)。

第一期产出: artworks_v2.json (对齐 kg-artworks.html 的 kg_artwork_v2.json 形态)。
后续可加: affect / worldview / language_vectors / subjects / artists 切片。

用法: python3 build_projections.py [--scope kept|exhibited] [--limit N]
"""
import os, json, argparse
from urllib.parse import quote
import psycopg2
from psycopg2.extras import RealDictCursor

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "web", "data", "live")
COS = "https://aha-1254041526.cos.ap-shanghai.myqcloud.com/"
# 库里 language7 长名 → kg-artworks 期望的短名
L7MAP = {"构图与组织": "构图", "透视与空间": "空间", "形状与造型": "造型", "光影与明暗": "光影",
         "色彩系统": "色彩", "笔触与肌理": "笔触", "边缘与节奏": "边缘"}

import re as _re0
def _numv(o):
    """从 language7 项稳健取 0-1 数值:支持 {v}/数字/畸形字符串('..v=0.9')。"""
    v = o.get("v") if isinstance(o, dict) else o
    try:
        f = float(v)
    except Exception:
        if isinstance(v, str):
            m = _re0.search(r"v\s*=\s*([01](?:\.\d+)?)", v) or _re0.search(r"([01](?:\.\d+)?)\s*$", v.strip())
            if not m: return None
            try: f = float(m.group(1))
            except Exception: return None
        else: return None
    return f if 0 <= f <= 1 else None

def pg():
    d = json.load(open(os.path.expanduser("~/.aha_pg.json")))
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

def img(cos_key, thumb=None):
    u = COS + quote(cos_key, safe="/")
    return u + f"?imageMogr2/thumbnail/{thumb}x/format/webp/quality/82" if thumb else u

def build_artworks(cur, scope, limit):
    where = "w.status='kept'" if scope == "kept" else "w.exhibited"
    cur.execute(f"""SELECT w.work_id, w.title, w.style_id, a.name_cn, a.name_en, w.vlm, f.cos_key
                    FROM works w JOIN artists a ON a.artist_id=w.artist_id
                    JOIN files f ON f.file_id=w.primary_file_id
                    WHERE {where} AND w.vlm IS NOT NULL
                    ORDER BY w.quality DESC NULLS LAST LIMIT %s""", (limit,))
    arts = {}
    for r in cur.fetchall():
        v = r["vlm"] or {}
        L7 = v.get("language7") or {}
        l7 = {}
        for full, short in L7MAP.items():
            fv = _numv(L7.get(full))
            if fv is not None: l7[short] = fv
        sid = str(r["work_id"])
        arts[sid] = {
            "slug": sid, "title": r["title"] or "无题",
            "artist": r["name_cn"] or r["name_en"] or "佚名",
            "style_id": r["style_id"],
            "thumb": img(r["cos_key"], 400), "full": img(r["cos_key"], 1280),
            "media": v.get("media"), "subject": v.get("subject"),
            "subject_tags": v.get("subject_tags") or [],
            "style": v.get("style") or {}, "reading": v.get("reading") or {},
            "language7": l7, "affect": v.get("affect") or {},
            "voiceover": v.get("voiceover"), "fused": v.get("fused"),
            "worldview": v.get("worldview") or {},
        }
    return {"meta": {"n": len(arts), "scope": scope, "source": "live · Postgres"}, "artworks": arts}

REGIONS = [  # kg_worldview_v3 六区中心,供世界观地图定位
    {"id": "WV1", "name": "摹写之眼", "cx": 0.232, "cy": 0.389},
    {"id": "WV2", "name": "礼制图式", "cx": 0.41, "cy": 0.287},
    {"id": "WV3", "name": "写意寄情", "cx": 0.528, "cy": 0.457},
    {"id": "WV4", "name": "经验之光", "cx": 0.533, "cy": 0.733},
    {"id": "WV5", "name": "表现外化", "cx": 0.775, "cy": 0.512},
    {"id": "WV6", "name": "形式建构", "cx": 0.82, "cy": 0.207},
]
def build_points(cur, scope, limit):
    where = "w.status='kept'" if scope == "kept" else "w.exhibited"
    cur.execute(f"""SELECT w.work_id, w.title, a.name_cn, a.name_en, s.name_zh style_zh, w.vlm, f.cos_key
                    FROM works w JOIN artists a ON a.artist_id=w.artist_id
                    JOIN files f ON f.file_id=w.primary_file_id LEFT JOIN styles s ON s.style_id=w.style_id
                    WHERE {where} AND w.vlm ? 'worldview' ORDER BY w.quality DESC NULLS LAST LIMIT %s""", (limit,))
    import re as _re
    pts = []
    for r in cur.fetchall():
        v = r["vlm"] or {}; wv = v.get("worldview") or {}; af = v.get("affect") or {}; vad = af.get("vad") or {}
        m = _re.search(r"WV[1-6]", str(wv.get("wv") or ""))
        if wv.get("x") is None or wv.get("y") is None: continue
        pts.append({"id": r["work_id"], "title": r["title"] or "无题",
                    "artist": r["name_cn"] or r["name_en"] or "佚名",
                    "thumb": img(r["cos_key"], 200), "wv": m.group(0) if m else None,
                    "x": wv.get("x"), "y": wv.get("y"),
                    "v": vad.get("valence"), "a": vad.get("arousal"),
                    "anchor": af.get("primary_anchor"), "style": r["style_zh"]})
    return {"meta": {"n": len(pts), "scope": scope}, "axes": {"x": "再现↔表现", "y": "结构↔感知"},
            "regions": REGIONS, "points": pts}

ANCHORS = "喜悦 鲜活 热烈 崇高 张力 恐惧 神秘 忧伤 孤独 怀旧 虚无 沉思 平静 空灵".split()
def build_affect(cur, scope, limit):
    where = "w.status='kept'" if scope == "kept" else "w.exhibited"
    cur.execute(f"""SELECT w.work_id, w.title, a.name_cn, a.name_en, s.name_zh style_zh, w.vlm, f.cos_key
                    FROM works w JOIN artists a ON a.artist_id=w.artist_id
                    JOIN files f ON f.file_id=w.primary_file_id LEFT JOIN styles s ON s.style_id=w.style_id
                    WHERE {where} AND w.vlm->'affect'->'vad' IS NOT NULL
                    ORDER BY w.quality DESC NULLS LAST LIMIT %s""", (limit,))
    pts = []
    for r in cur.fetchall():
        v = r["vlm"] or {}; af = v.get("affect") or {}; vad = af.get("vad") or {}
        if vad.get("valence") is None or vad.get("arousal") is None: continue
        pts.append({"id": r["work_id"], "title": r["title"] or "无题",
                    "artist": r["name_cn"] or r["name_en"] or "佚名", "thumb": img(r["cos_key"], 200),
                    "v": vad.get("valence"), "a": vad.get("arousal"), "d": vad.get("dominance"),
                    "anchor": af.get("primary_anchor"), "style": r["style_zh"]})
    return {"meta": {"n": len(pts), "scope": scope}, "anchors": ANCHORS,
            "axes": {"x": "消极↔积极(愉悦)", "y": "平静↔激越(唤起)"}, "points": pts}

def build_subjects(cur, top=60):
    """题材聚合:kept 作品 subject_tags 计数 + 每题材几张样图。"""
    cur.execute("""SELECT w.vlm->'subject_tags' tags, f.cos_key FROM works w
                   JOIN files f ON f.file_id=w.primary_file_id
                   WHERE w.status='kept' AND w.vlm ? 'subject_tags'""")
    cnt = {}; samp = {}
    for r in cur.fetchall():
        tags = r["tags"] or []
        if not isinstance(tags, list): continue
        for t in tags:
            if not t or not isinstance(t, str): continue
            t = t.strip()
            if not t: continue
            cnt[t] = cnt.get(t, 0) + 1
            if len(samp.setdefault(t, [])) < 4: samp[t].append(img(r["cos_key"], 200))
    items = [{"tag": t, "n": n, "samples": samp.get(t, [])} for t, n in
             sorted(cnt.items(), key=lambda x: -x[1])[:top]]
    return {"meta": {"n": len(cnt), "shown": len(items)}, "subjects": items}

def build_aggregates(cur):
    """一次拉 kept 作品,聚合出 风格指纹(styles) + 艺术家情绪重心(artists)。"""
    cur.execute("""SELECT w.style_id, s.name_zh style_zh, w.artist_id, a.name_cn, a.name_en, w.vlm, f.cos_key
                   FROM works w JOIN artists a ON a.artist_id=w.artist_id
                   JOIN files f ON f.file_id=w.primary_file_id LEFT JOIN styles s ON s.style_id=w.style_id
                   WHERE w.status='kept' AND w.vlm IS NOT NULL""")
    import re as _re
    SD = {}  # style
    AD = {}  # artist
    for r in cur.fetchall():
        v = r["vlm"] or {}; L7 = v.get("language7") or {}; af = v.get("affect") or {}; vad = af.get("vad") or {}
        wv = v.get("worldview") or {}; mw = _re.search(r"WV[1-6]", str(wv.get("wv") or ""))
        # style 聚合
        sid = r["style_id"]
        if sid:
            d = SD.setdefault(sid, {"name": r["style_zh"], "n": 0, "lang": {s: [0, 0] for s in L7MAP.values()},
                                    "vad": [0, 0, 0, 0], "wv": {}})
            d["n"] += 1
            for full, short in L7MAP.items():
                fv = _numv(L7.get(full))
                if fv is not None: d["lang"][short][0] += fv; d["lang"][short][1] += 1
            if vad.get("valence") is not None:
                d["vad"][0] += float(vad["valence"]); d["vad"][1] += float(vad.get("arousal") or 0)
                d["vad"][2] += float(vad.get("dominance") or 0); d["vad"][3] += 1
            if mw: d["wv"][mw.group(0)] = d["wv"].get(mw.group(0), 0) + 1
        # artist 聚合(情绪重心)
        aid = r["artist_id"]
        ad = AD.setdefault(aid, {"name": r["name_cn"] or r["name_en"] or "佚名", "n": 0,
                                 "v": 0, "a": 0, "vn": 0, "styles": {}, "thumb": img(r["cos_key"], 200)})
        ad["n"] += 1
        if vad.get("valence") is not None:
            ad["v"] += float(vad["valence"]); ad["a"] += float(vad.get("arousal") or 0); ad["vn"] += 1
        if r["style_zh"]: ad["styles"][r["style_zh"]] = ad["styles"].get(r["style_zh"], 0) + 1
    styles = []
    for sid, d in SD.items():
        styles.append({"id": sid, "name": d["name"], "n": d["n"],
                       "lang": {k: round(x[0] / x[1], 3) if x[1] else None for k, x in d["lang"].items()},
                       "vad": {"v": round(d["vad"][0] / d["vad"][3], 3), "a": round(d["vad"][1] / d["vad"][3], 3),
                               "d": round(d["vad"][2] / d["vad"][3], 3)} if d["vad"][3] else None,
                       "wv": max(d["wv"], key=d["wv"].get) if d["wv"] else None})
    styles.sort(key=lambda s: -s["n"])
    artists = []
    for aid, d in AD.items():
        if d["n"] < 3: continue
        artists.append({"id": aid, "name": d["name"], "n": d["n"], "thumb": d["thumb"],
                        "v": round(d["v"] / d["vn"], 3) if d["vn"] else None,
                        "a": round(d["a"] / d["vn"], 3) if d["vn"] else None,
                        "style": max(d["styles"], key=d["styles"].get) if d["styles"] else None})
    artists.sort(key=lambda x: -x["n"])
    return ({"meta": {"n": len(styles)}, "styles": styles},
            {"meta": {"n": len(artists)}, "artists": artists})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="kept", choices=["kept", "exhibited"])
    ap.add_argument("--limit", type=int, default=4000)
    a = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    cn = pg(); cur = cn.cursor(cursor_factory=RealDictCursor)
    data = build_artworks(cur, a.scope, a.limit)
    path = os.path.join(OUT_DIR, "artworks_v2.json")
    json.dump(data, open(path, "w"), ensure_ascii=False)
    print(f"✓ artworks_v2.json  {data['meta']['n']} 件 (scope={a.scope})")
    # 精简索引:网格用,只留卡片要的字段(全字段详情留给 artworks_v2.json 懒加载)
    idx = {"meta": dict(data["meta"], kind="index"),
           "artworks": {k: {"slug": v["slug"], "title": v["title"], "artist": v["artist"],
                            "thumb": v["thumb"], "anchor": (v.get("affect") or {}).get("primary_anchor")}
                        for k, v in data["artworks"].items()}}
    json.dump(idx, open(os.path.join(OUT_DIR, "artworks_index.json"), "w"), ensure_ascii=False)
    print(f"✓ artworks_index.json  {len(idx['artworks'])} 件(精简索引,网格用)")
    pts = build_points(cur, a.scope, max(a.limit, 20000))
    json.dump(pts, open(os.path.join(OUT_DIR, "points.json"), "w"), ensure_ascii=False)
    print(f"✓ points.json  {pts['meta']['n']} 点(含世界观坐标)")
    aff = build_affect(cur, a.scope, max(a.limit, 20000))
    json.dump(aff, open(os.path.join(OUT_DIR, "affect.json"), "w"), ensure_ascii=False)
    print(f"✓ affect.json  {aff['meta']['n']} 点(含VAD)")
    subj = build_subjects(cur)
    json.dump(subj, open(os.path.join(OUT_DIR, "subjects.json"), "w"), ensure_ascii=False)
    print(f"✓ subjects.json {subj['meta']['n']} 题材")
    sty, art = build_aggregates(cur)
    json.dump(sty, open(os.path.join(OUT_DIR, "styles.json"), "w"), ensure_ascii=False)
    json.dump(art, open(os.path.join(OUT_DIR, "artists.json"), "w"), ensure_ascii=False)
    print(f"✓ styles.json {sty['meta']['n']} 风格 · artists.json {art['meta']['n']} 艺术家(≥3作)")
    cn.close()

if __name__ == "__main__":
    main()
