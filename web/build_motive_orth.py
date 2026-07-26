#!/usr/bin/env python3
"""
build_motive_orth.py —— 量化「动机 ⊥ 感知」正交性(science.html 第三幕 / kg_science.json motive-orth)。

思路:动机是类别变量(5 型 V1–V5),VAD 是连续三维。类别→连续的关联强度
用相关比 η²(eta-squared,= 组间方差 / 总方差,0..1)。
- η² 很低  → 知道动机几乎推不出 VAD,两轴近乎独立(强正交)。
- η² 中等  → 动机能解释 VAD 的一部分,但远非全部(部分正交,仍是两根轴)。
- η² 很高  → 动机几乎决定 VAD,两者塌成一根轴(不正交)。

动机归型完全复刻 kg-subtext.html 的 inferKeyword(关键词命中计分),
只用真数据(kg_artists.json 的 affect + kg_subtext_motive.json 的 words/quick_map),
不引入任何手填数字。
"""
import json
from collections import defaultdict

AD = json.load(open("data/kg_artists.json"))["artists"]
MO = json.load(open("data/kg_subtext_motive.json"))

arts = [a for a in AD.values() if a and a.get("affect") and a["affect"].get("v") is not None]
qmap = MO.get("quick_map", {})
GENERIC = {"再现": 1, "见证": 1, "平静": 1, "喜悦": 1}  # 同 kg-subtext:过通用词剔除
wordsOf = {t["id"]: [w for w in (t.get("words") or []) if w not in GENERIC] for t in MO["types"]}


def infer_keyword(a):
    txt = " ".join([a.get("meaning") or "", a.get("quote") or "",
                    a.get("headline") or "", " ".join(a.get("subjects") or [])])
    score = {k: 0 for k in ("V1", "V2", "V3", "V4", "V5")}
    for tid, ws in wordsOf.items():
        for w in ws:
            if w and w in txt:
                score[tid] += 1
    for kw, tid in qmap.items():
        if kw not in GENERIC and kw in txt:
            score[tid] = score.get(tid, 0) + 1
    best, bv = None, 0
    for tid, v in score.items():
        if v > bv:
            bv, best = v, tid
    return best if bv > 0 else None


rows = []  # (tid, v, a, d)
for a in arts:
    tid = infer_keyword(a)
    af = a["affect"]
    if tid and all(k in af for k in ("v", "a", "d")):
        rows.append((tid, af["v"], af["a"], af["d"]))


def eta2(idx):
    vals = [r[1 + idx] for r in rows]
    groups = defaultdict(list)
    for r in rows:
        groups[r[0]].append(r[1 + idx])
    grand = sum(vals) / len(vals)
    sstot = sum((x - grand) ** 2 for x in vals)
    ssb = sum(len(g) * ((sum(g) / len(g)) - grand) ** 2 for g in groups.values())
    return ssb / sstot if sstot else 0.0


gc = defaultdict(int)
for r in rows:
    gc[r[0]] += 1

axes = {"valence": eta2(0), "arousal": eta2(1), "dominance": eta2(2)}
mean_eta = sum(axes.values()) / 3

out = {
    "method": "motive(5型类别) -> VAD(连续三维) 的相关比 eta^2 = 组间方差/总方差",
    "n_classified": len(rows),
    "n_total_with_vad": len(arts),
    "group_sizes": dict(sorted(gc.items())),
    "eta2": {k: round(v, 3) for k, v in axes.items()},
    "eta2_mean": round(mean_eta, 3),
}
print(json.dumps(out, ensure_ascii=False, indent=2))

with open("data/kg_motive_orth.json", "w") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("\nwrote data/kg_motive_orth.json")
