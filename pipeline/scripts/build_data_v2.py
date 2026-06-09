#!/usr/bin/env python3
"""深度富集 + 自动建图。
- 富集:主色(rgb/hsl)、情绪(valence/arousal)、年代、流派、母题。
- 建图:自动边(同艺术家/同流派/色彩呼应/同母题)+ 保留原18件手工影响边。
- 原18件:沿用手工 themes/oneLiner/look,并补上颜色/情绪等新字段。
输出 data/artworks.json + data/graph.json。"""
import json, math, colorsys, re
from collections import defaultdict, deque
ROOT = "/home/ubuntu/users/qiuyiwu/aha-art-demo/data/"

rich = json.load(open(ROOT + "artworks_rich.json"))
orig_raw = {w["slug"]: w for w in json.load(open(ROOT + "artworks_raw.json"))}        # slug→{aicId,...}
orig_final = {w["slug"]: w for w in json.load(open(ROOT + "curated18.json"))}         # 冻结:18件策展内容(幂等)
orig_edges = json.load(open(ROOT + "curated_edges.json"))["edges"]                    # 冻结:手工边
aic2slug = {orig_raw[s]["aicId"]: s for s in orig_raw}                                 # aicId→原slug
CUR = {orig_raw[s]["aicId"]: {"slug": s, "themes": orig_final[s]["themes"],
        "oneLiner": orig_final[s]["oneLiner"], "look": orig_final[s]["look"]} for s in orig_raw}

# 确保原18件在语料里(rich 没抓到的,用旧数据补)
rich_ids = {w["aicId"] for w in rich}
for s, w in orig_final.items():
    aid = orig_raw[s]["aicId"]
    if aid not in rich_ids:
        rich.append({"aicId": aid, "title": w["title"], "artist": w["artist"], "artistId": None,
                     "date": w.get("date"), "year": w.get("year"), "medium": w.get("medium"),
                     "classification": w.get("classification"), "styles": [], "subjects": [],
                     "themesRaw": [], "origin": w.get("origin"), "type": None, "color": None,
                     "colorfulness": None, "image": w["image"], "lqip": w.get("lqip"), "alt": w.get("alt")})

# ── 富集助手 ──
def hsl_of(c):
    if not c: return (210.0, 0.10, 0.52)
    return (float(c["h"]), c["s"] / 100.0, c["l"] / 100.0)
def rgb_of(h, s, l):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l, s)
    return [round(r * 255), round(g * 255), round(b * 255)]
def warmth(h):  # 1≈橙(40°) 0≈蓝(220°)
    return (math.cos(math.radians(h - 40)) + 1) / 2
def clamp(x): return max(0.0, min(1.0, x))
def mood_of(h, s, l, cf):
    val = clamp(0.28 + 0.5 * l + 0.22 * warmth(h))
    aro = clamp(0.20 + 0.55 * s + 0.25 * min((cf or 0) / 80.0, 1))
    return round(val, 2), round(aro, 2)
def century(y):
    if y is None: return None
    return (y // 100 + 1) if y > 0 else (y // 100 - 1)

GENERIC = ("century", "european", "nineteenth", "twentieth")
def clean_style(w):
    for st in (w.get("styles") or []):
        s2 = st.replace(" (culture or style)", "").strip()
        if any(g in s2.lower() for g in GENERIC): continue
        return s2
    return None

SUBJ_MAP = {  # AIC 题材关键词(子串) → 受控母题
    "portrait": "人物", "men": "人物", "man": "人物", "women": "人物", "woman": "人物", "people": "人物",
    "children": "童真", "child": "童真", "mother": "母与子",
    "landscape": "自然", "tree": "自然", "weather": "自然", "season": "自然", "garden": "自然", "flower": "花卉",
    "water": "海", "marine": "海", "sea": "海", "river": "海", "ship": "海",
    "still life": "静物", "fruit": "静物",
    "animal": "动物", "horse": "动物", "bird": "动物",
    "religio": "灵性", "christ": "灵性", "saint": "灵性", "god": "灵性", "myth": "神话",
    "night": "夜", "city": "都市", "street": "都市", "urban": "都市", "dance": "夜生活", "music": "夜生活",
    "nude": "人体", "war": "动荡", "death": "动荡", "labor": "日常", "work": "日常", "interior": "私密",
}
def themes_of(w, hsl):
    ts = []
    pool = [s.lower() for s in (w.get("subjects") or []) + (w.get("themesRaw") or [])]
    for s in pool:
        for k, v in SUBJ_MAP.items():
            if k in s and v not in ts: ts.append(v)
    h, s_, l = hsl
    if l > 0.6: ts.append("明亮")
    elif l < 0.32: ts.append("幽暗")
    if warmth(h) > 0.6 and s_ > 0.25: ts.append("暖")
    elif warmth(h) < 0.35 and s_ > 0.2: ts.append("冷")
    if not ts: ts.append(w.get("classification") or "作品")
    out = []
    for t in ts:
        if t not in out: out.append(t)
    return out[:5]

def color_word(h, s, l):
    if s < 0.12: return ("明亮的灰" if l > 0.55 else "幽暗的灰")
    name = ("红" if h < 20 or h >= 330 else "暖橙" if h < 50 else "金黄" if h < 70 else
            "绿" if h < 160 else "青" if h < 200 else "蓝" if h < 255 else "紫")
    return ("明" if l > 0.6 else "暗" if l < 0.33 else "") + name

# ── 组装作品 ──
works, used_slug = [], set()
def mk_slug(aid):
    return aic2slug.get(aid) or ("w" + str(aid))
for w in rich:
    aid = w["aicId"]; slug = mk_slug(aid)
    if slug in used_slug: continue
    used_slug.add(slug)
    hsl = hsl_of(w.get("color")); h, s, l = hsl
    val, aro = mood_of(h, s, l, w.get("colorfulness"))
    cur = CUR.get(aid)
    if cur:
        themes, one, look = cur["themes"], cur["oneLiner"], cur["look"]
    else:
        themes = themes_of(w, hsl)
        st = clean_style(w); typ = w.get("type") or w.get("classification") or "作品"
        subj = (w.get("subjects") or [None])[0]
        one = f"{(st + '的') if st else ''}{typ}" + (f",关于{subj}" if subj else "") + f"。{w.get('artist') or ''}{('·' + w['date']) if w.get('date') else ''}"
        look = f"留意它{color_word(h, s, l)}的色调与" + ("、".join(themes[:2]) if themes else "构成") + "。"
    works.append({
        "slug": slug, "title": w["title"], "artist": w.get("artist"), "date": w.get("date"),
        "year": w.get("year"), "century": century(w.get("year")),
        "medium": w.get("medium"), "origin": w.get("origin"),
        "style": clean_style(w), "themes": themes,
        "image": w["image"], "thumb": re.sub(r"/\d+,/", "/200,/", w["image"]), "lqip": w.get("lqip"), "alt": w.get("alt"),
        "color": {"rgb": rgb_of(h, s, l), "hsl": [round(h), round(s, 2), round(l, 2)]},
        "mood": {"valence": val, "arousal": aro},
        "oneLiner": one, "look": look,
    })

BY = {w["slug"]: w for w in works}
slugs = set(BY)

# ── 边:手工 + 自动 ──
adj = defaultdict(set)
edges = []
DEG_CAP = 7
def add(a, b, typ, why):
    if a == b or a not in slugs or b not in slugs: return
    key = tuple(sorted((a, b)))
    if key in seen_e: return
    if typ != "influence" and (len(adj[a]) >= DEG_CAP or len(adj[b]) >= DEG_CAP): return
    seen_e.add(key); adj[a].add(b); adj[b].add(a)
    edges.append({"a": a, "b": b, "type": typ, "why": why})
seen_e = set()

# 1) 手工影响/母题边(原18,优先)
for e in orig_edges:
    if e["a"] in slugs and e["b"] in slugs:
        add(e["a"], e["b"], e["type"], e["why"])

# 2) 同艺术家(按年代串成链,避免完全图)
byart = defaultdict(list)
for w in works:
    if w["artist"]: byart[w["artist"]].append(w)
for art, ws in byart.items():
    ws.sort(key=lambda x: x.get("year") or 0)
    for i in range(len(ws) - 1):
        add(ws[i]["slug"], ws[i + 1]["slug"], "artist", f"同是{art}的作品。")

# 3) 同流派(各连最近年代的 2 件)
bystyle = defaultdict(list)
for w in works:
    if w["style"]: bystyle[w["style"]].append(w)
for st, ws in bystyle.items():
    if len(ws) < 2: continue
    for w in ws:
        others = sorted([o for o in ws if o is not w], key=lambda o: abs((o.get("year") or 0) - (w.get("year") or 0)))
        for o in others[:2]:
            add(w["slug"], o["slug"], "movement", f"同属{st}。")

# 4) 同母题(跨流派优先,各连 2 件)
def cdist(a, b):
    dh = abs(a[0] - b[0]); dh = min(dh, 360 - dh) / 180
    return dh * 1.4 + abs(a[1] - b[1]) + abs(a[2] - b[2]) * 0.8
for w in works:
    cands = []
    for o in works:
        if o is w: continue
        shared = set(w["themes"]) & set(o["themes"])
        if shared:
            cands.append((len(shared), -abs((o.get("year") or 0) - (w.get("year") or 0)), o, next(iter(shared))))
    cands.sort(key=lambda x: (-x[0], x[1]))
    for _, _, o, sh in cands[:2]:
        add(w["slug"], o["slug"], "theme", f"同母题:{sh}。")

# 5) 形式呼应:跨流派的色彩相近(各连 2 件)
for w in works:
    wc = w["color"]["hsl"]
    cands = sorted([o for o in works if o is not w and o["style"] != w["style"]],
                   key=lambda o: cdist(wc, o["color"]["hsl"]))
    for o in cands[:2]:
        h, s, l = w["color"]["hsl"]
        add(w["slug"], o["slug"], "formal", f"色彩气质相近(都偏{color_word(h, s, l)})。")

# 6) 救援:任何孤立点强连到最近色彩邻居(忽略度上限)
for w in works:
    if len(adj[w["slug"]]) == 0:
        wc = w["color"]["hsl"]
        o = min((x for x in works if x is not w), key=lambda x: cdist(wc, x["color"]["hsl"]))
        key = tuple(sorted((w["slug"], o["slug"])))
        if key not in seen_e:
            seen_e.add(key); adj[w["slug"]].add(o["slug"]); adj[o["slug"]].add(w["slug"])
            edges.append({"a": w["slug"], "b": o["slug"], "type": "formal", "why": "色彩气质相近。"})

TYPE_LABEL = {"influence": "影响", "theme": "同母题", "formal": "形式呼应", "artist": "同艺术家", "movement": "同流派"}
graph = {"typeLabels": TYPE_LABEL, "edges": edges}

json.dump(works, open(ROOT + "artworks.json", "w"), ensure_ascii=False, indent=1)
json.dump(graph, open(ROOT + "graph.json", "w"), ensure_ascii=False, indent=1)

# ── 自检 ──
start = next(iter(slugs)); seen = {start}; q = deque([start])
while q:
    for n in adj[q.popleft()]:
        if n not in seen: seen.add(n); q.append(n)
deg = [len(adj[s]) for s in slugs]
from collections import Counter
tc = Counter(e["type"] for e in edges)
print(f"作品 {len(works)} · 边 {len(edges)} · 连通 {len(seen)}/{len(slugs)}")
print(f"边类型: {dict(tc)}")
print(f"度: min {min(deg)} / 平均 {sum(deg)/len(deg):.1f} / max {max(deg)} · 孤立点 {sum(1 for d in deg if d==0)}")
print(f"有颜色 {sum(1 for w in works if w['color'])} · 有流派 {sum(1 for w in works if w['style'])} · 母题去重 {len(set(t for w in works for t in w['themes']))} 种")
