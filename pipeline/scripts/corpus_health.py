#!/usr/bin/env python3
# 语料体检 + 校准集生成
# 1) 量出语料在审美 4 轴(明暗/冷暖/静动/古今)上的偏斜与覆盖
# 2) 用最远点采样(FPS)挑一个"铺满空间"的校准集,写入 data/calib.json
import json, math, os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
works = json.load(open(os.path.join(ROOT, 'data/artworks.json'), encoding='utf-8'))

def feat(w):
    if not w.get('color') or not w.get('mood'):
        return None
    h, s, l = w['color']['hsl']
    warm_hue = 0.5 + 0.5 * math.cos(math.radians(h - 40))
    warm = max(0.0, min(1.0, 0.5 * (warm_hue * (0.35 + 0.65 * s)) + 0.5 * w['mood'].get('valence', 0.5)))
    energy = w['mood'].get('arousal', 0.4)
    modern = max(0.0, min(1.0, ((w.get('century') or 18) - 15) / 6))
    return [l, warm, energy, modern]

AX = ['明暗(暗→明)', '冷暖(冷→暖)', '静动(静→动)', '古今(古→今)']
feats = [(w['slug'], feat(w)) for w in works]
feats = [(s, f) for s, f in feats if f]
N = len(feats)
print(f'== 语料体检:{N} 件有完整特征(共 {len(works)} 件)==\n')

# 各轴分布(分 4 桶看是否铺满)
print('— 各轴覆盖(理想:四桶都均匀)—')
for i, name in enumerate(AX):
    buckets = Counter(min(3, int(f[i] * 4)) for _, f in feats)
    vals = [f[i] for _, f in feats]
    bar = ' '.join(f'{buckets.get(b,0):>2}' for b in range(4))
    print(f'  {name:14s} 桶[低 中低 中高 高]= {bar}   范围 {min(vals):.2f}–{max(vals):.2f}  均值 {sum(vals)/N:.2f}')

# 母题/世纪偏斜
th = Counter(t for w in works for t in (w.get('themes') or []))
print('\n— 母题偏斜(前 8)—')
for t, c in th.most_common(8):
    print(f'  #{t:6s} {c:>3}  ({c*100//len(works)}%)')
cent = Counter(w.get('century') for w in works)
print('\n— 世纪偏斜 —  ', dict(sorted(cent.items(), key=lambda x: -x[1])))

# 偏斜诊断:哪些区域稀缺(要补的方向)
def cnt(pred): return sum(1 for _, f in feats if pred(f))
print('\n— 稀缺区域诊断(占比偏低=需补)—')
diag = [
    ('明亮画 light>0.6', cnt(lambda f: f[0] > 0.6)),
    ('幽暗画 light<0.35', cnt(lambda f: f[0] < 0.35)),
    ('冷色 warm<0.4', cnt(lambda f: f[1] < 0.4)),
    ('高能/动 energy>0.6', cnt(lambda f: f[2] > 0.6)),
    ('安静 energy<0.35', cnt(lambda f: f[2] < 0.35)),
    ('古典 modern<0.4', cnt(lambda f: f[3] < 0.4)),
    ('近现代 modern>0.7', cnt(lambda f: f[3] > 0.7)),
]
for name, c in diag:
    flag = '  ⚠️ 稀缺' if c < N * 0.15 else ''
    print(f'  {name:22s} {c:>3}  ({c*100//N}%){flag}')

# 最远点采样:挑铺满空间的校准集
def dist(a, b): return math.sqrt(sum((a[i]-b[i])**2 for i in range(4)))
K = min(30, N)
# 从最"极端"的点起步(离全局质心最远)
cz = [sum(f[i] for _, f in feats)/N for i in range(4)]
start = max(range(N), key=lambda j: dist(feats[j][1], cz))
chosen = [start]
while len(chosen) < K:
    best, bestd = -1, -1
    for j in range(N):
        if j in chosen: continue
        d = min(dist(feats[j][1], feats[c][1]) for c in chosen)
        if d > bestd: bestd, best = d, j
    chosen.append(best)
calib = [feats[j][0] for j in chosen]
json.dump(calib, open(os.path.join(ROOT, 'data/calib.json'), 'w', encoding='utf-8'), ensure_ascii=False)

# 校准集覆盖 vs 全集
print(f'\n== 校准集(FPS 铺满空间,{K} 件)已写入 data/calib.json ==')
print('— 校准集各轴覆盖(应比全集更均匀)—')
cf = [feats[j][1] for j in chosen]
for i, name in enumerate(AX):
    buckets = Counter(min(3, int(f[i] * 4)) for f in cf)
    print(f'  {name:14s} 桶= {" ".join(f"{buckets.get(b,0):>2}" for b in range(4))}')
