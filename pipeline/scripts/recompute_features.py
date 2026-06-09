#!/usr/bin/env python3
# 从真实像素重算 mood(arousal/valence)与主色,并做分位归一化铺满审美空间。
# 根因:原 arousal/valence 由颜色粗估、被压平 → 静动/冷暖轴测不出。
import json, os, math, statistics
from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMGDIR = '/data/pub/p/aha/img'
works = json.load(open(os.path.join(ROOT, 'data/artworks.json'), encoding='utf-8'))

def analyze(slug):
    p = os.path.join(IMGDIR, slug + '.jpg')
    if not os.path.exists(p):
        return None
    im = Image.open(p).convert('RGB'); im.thumbnail((140, 140))
    rgb = list(im.getdata()); n = len(rgb)
    hsv = list(im.convert('HSV').getdata())
    S = [c[1] / 255 for c in hsv]; V = [c[2] / 255 for c in hsv]; H = [c[0] / 255 * 360 for c in hsv]
    sat_mean = sum(S) / n; val_mean = sum(V) / n
    val_std = statistics.pstdev(V)
    # 暖度:在有彩色像素上算暖色相占比(红橙黄=暖)
    warm_w = warm_s = 0.0
    for h, s in zip(H, S):
        if s > 0.18:
            warm = 0.5 + 0.5 * math.cos(math.radians(h - 40))
            warm_w += warm * s; warm_s += s
    warmth = (warm_w / warm_s) if warm_s else 0.5
    # 色彩丰富度 Hasler–Süsstrunk
    rg = [c[0] - c[1] for c in rgb]; yb = [0.5 * (c[0] + c[1]) - c[2] for c in rgb]
    colorful = (math.sqrt(statistics.pvariance(rg) + statistics.pvariance(yb)) +
                0.3 * math.sqrt((sum(rg) / n) ** 2 + (sum(yb) / n) ** 2)) / 255
    # 边缘密度
    edges = im.convert('L').filter(ImageFilter.FIND_EDGES)
    ed = list(edges.getdata()); edge = (sum(ed) / len(ed)) / 255
    # 主色:有彩色像素的圆形平均色相 + 平均饱和
    xs = ys = ssum = 0.0; cnt = 0
    for h, s in zip(H, S):
        if s > 0.2:
            xs += math.cos(math.radians(h)) * s; ys += math.sin(math.radians(h)) * s; ssum += s; cnt += 1
    if cnt and ssum:
        dom_h = math.degrees(math.atan2(ys, xs)) % 360; dom_s = ssum / cnt
    else:
        dom_h = 30; dom_s = sat_mean
    return dict(sat=sat_mean, val=val_mean, contrast=val_std, warmth=warmth,
               colorful=min(1, colorful), edge=edge, dom_h=dom_h, dom_s=min(1, dom_s))

feat = {}
for w in works:
    a = analyze(w['slug'])
    if a: feat[w['slug']] = a
print(f'分析 {len(feat)}/{len(works)} 张图')

# 原始 arousal / valence(基于真正会变化的像素信号)
raw_ar = {s: 0.34 * a['sat'] + 0.26 * a['contrast'] * 2 + 0.24 * a['colorful'] + 0.16 * a['edge'] for s, a in feat.items()}
raw_va = {s: 0.45 * a['val'] + 0.30 * a['warmth'] + 0.25 * a['sat'] for s, a in feat.items()}

def rank_norm(d, lo=0.05, hi=0.95):
    order = sorted(d, key=lambda k: d[k]); m = len(order)
    return {k: round(lo + (hi - lo) * (i / (m - 1)), 3) for i, k in enumerate(order)}

ar = rank_norm(raw_ar); va = rank_norm(raw_va)
# light(明暗)也分位归一化铺满,用整体亮度
li = rank_norm({s: a['val'] for s, a in feat.items()})

for w in works:
    a = feat.get(w['slug'])
    if not a: continue
    w['mood'] = {'valence': va[w['slug']], 'arousal': ar[w['slug']]}
    # 主色:色相/饱和来自像素,明度用分位归一后的整体亮度(=明暗轴)
    import colorsys
    rgb = colorsys.hls_to_rgb(a['dom_h'] / 360, li[w['slug']], min(0.9, a['dom_s']))
    w['color'] = {'rgb': [round(x * 255) for x in rgb], 'hsl': [round(a['dom_h'], 1), round(min(0.9, a['dom_s']), 3), li[w['slug']]]}

json.dump(works, open(os.path.join(ROOT, 'data/artworks.json'), 'w', encoding='utf-8'), ensure_ascii=False)
print('已写回 data/artworks.json')
# 体检新分布
for name, d in [('arousal(静动)', ar), ('valence', va), ('light(明暗)', li)]:
    vals = list(d.values())
    print(f'  {name:16s} 范围 {min(vals):.2f}–{max(vals):.2f} 均值 {sum(vals)/len(vals):.2f}')
