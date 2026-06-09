#!/usr/bin/env python3
"""把你们 KG 的真实标注并入 artworks.json —— brain v0.3 会自动启用最深的维度。

用法:
  python3 scripts/merge_kg.py [annotations.json] [artworks.json]
  默认读 data/kg_annotations.json,写回 data/artworks.json。

标注文件 = 一个数组,每条对应一幅画,按 slug(优先)或 title+artist 匹配。字段:
  {
    "slug": "m436965",                 # 优先用 slug(= 'm'+Met objectID);没有就给 title+artist
    "title": "...", "artist": "...",
    "styleVec": [0.4, -0.2, 0.6, 0.1], # 风格 4 轴 [再现↔表现, 结构↔感知, 秩序↔张力, 节制↔强度],各 −1..1
    "worldModel": "W3",                # W1–W6(或东方谱系码)
    "voice": "情绪表达型",              # 5 类画外音之一
    "themes": ["光","孤独"]            # 可选,追加进 themes
  }
只填你有的字段即可;缺的不动。brain:styleVec→风格轴质心(Aha 距离最深维度)、
worldModel→桥/成长、voice→画像。"""
import json, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANN = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'data/kg_annotations.json')
ART = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'data/artworks.json')

works = json.load(open(ART, encoding='utf-8'))
by_slug = {w['slug']: w for w in works}
by_ta = {(w.get('title', '').strip().lower(), (w.get('artist') or '').strip().lower()): w for w in works}
ann = json.load(open(ANN, encoding='utf-8'))

matched = unmatched = 0; errs = []
for a in ann:
    if isinstance(a, dict) and a.get('_README'):
        continue
    w = by_slug.get(a.get('slug')) or by_ta.get((a.get('title', '').strip().lower(), (a.get('artist') or '').strip().lower()))
    if not w:
        unmatched += 1; errs.append('未匹配: ' + (a.get('slug') or a.get('title', '?'))); continue
    if 'styleVec' in a:
        v = a['styleVec']
        if not (isinstance(v, list) and len(v) == 4 and all(isinstance(x, (int, float)) and -1.01 <= x <= 1.01 for x in v)):
            errs.append('styleVec 非法(需4个 −1..1): ' + w['slug']); continue
        w['styleVec'] = [round(float(x), 3) for x in v]
    if a.get('worldModel'): w['worldModel'] = str(a['worldModel'])
    if a.get('voice'): w['voice'] = str(a['voice'])
    if a.get('themes'):
        w['themes'] = list(dict.fromkeys((w.get('themes') or []) + list(a['themes'])))[:6]
    matched += 1

json.dump(works, open(ART, 'w', encoding='utf-8'), ensure_ascii=False)
cov = {k: sum(1 for w in works if w.get(k)) for k in ('styleVec', 'worldModel', 'voice')}
print(f'并入完成:匹配 {matched} · 未匹配 {unmatched} → 写回 {ART}')
print(f'覆盖:styleVec {cov["styleVec"]}/{len(works)} · worldModel {cov["worldModel"]} · voice {cov["voice"]}')
for e in errs[:10]: print('  ⚠️', e)
