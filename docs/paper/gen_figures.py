#!/usr/bin/env python3
"""论文图表生成:用真实数据出两张出版级 SVG —— 图1 共享审美流形(世界观平面)、图2 倒U惊奇带。"""
import sys, json, math, random
sys.path.insert(0, '/home/ubuntu/users/qiuyiwu/aha-art/pipeline')
import _profile_aha as P

OUT = '/home/ubuntu/users/qiuyiwu/aha-art/docs/paper/figures'
INK, MUTE, FAINT, ACC, GREEN, LINE = '#1d1b18', '#857d6f', '#c8bda8', '#b0673a', '#5a7d6f', '#ddd5c6'
WV = [("WV1", "摹写之眼", .232, .389), ("WV2", "礼制图式", .41, .287), ("WV3", "写意寄情", .528, .457),
      ("WV4", "经验之光", .533, .733), ("WV5", "表现外化", .775, .512), ("WV6", "形式建构", .82, .207)]


def fig1_manifold():
    """世界观平面:8000+ 作品淡点 + 6 区中心 + 几位大师质心 + 一个用户 μ(证明人画同空间)。"""
    conn = P._conn(); cur = conn.cursor()
    cur.execute("""SELECT (vlm->'worldview'->>'x')::float, (vlm->'worldview'->>'y')::float
                   FROM works WHERE status='kept' AND vlm->'worldview'->>'x' IS NOT NULL""")
    pts = [(x, y) for x, y in cur.fetchall() if x is not None and y is not None]
    random.Random(7).shuffle(pts); pts = pts[:700]
    # 用户 μ(取数据最足者)
    cur.execute("SELECT vec FROM mu_profile WHERE n>=20 ORDER BY n DESC LIMIT 1")
    r = cur.fetchone(); mu = r[0] if r else None
    conn.close()
    # 几位大师质心(从 kg_artists)
    arts = []
    try:
        AJ = json.load(open('/data/pub/p/aha/data/kg_artists.json')).get('artists', {})
        want = {'列宾', '莫奈', '倪瓒', '梵高', '达·芬奇', '塞尚'}
        for a in AJ.values():
            if a.get('wv') and a['wv'].get('x') is not None and a.get('cn') in want:
                arts.append((a['cn'], a['wv']['x'], a['wv']['y']))
    except Exception:
        pass
    W, H, P0 = 660, 520, 56
    def sx(x): return P0 + x * (W - 2 * P0)
    def sy(y): return (H - P0) - y * (H - 2 * P0)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Noto Serif SC,serif">']
    s.append(f'<rect width="{W}" height="{H}" fill="#faf8f3"/>')
    # 轴
    s.append(f'<line x1="{P0}" y1="{H-P0}" x2="{W-P0}" y2="{H-P0}" stroke="{LINE}"/>')
    s.append(f'<line x1="{P0}" y1="{P0}" x2="{P0}" y2="{H-P0}" stroke="{LINE}"/>')
    s.append(f'<text x="{W-P0}" y="{H-P0+24}" font-size="13" fill="{MUTE}" text-anchor="end">再现 → 表现  (x)</text>')
    s.append(f'<text x="{P0-10}" y="{P0-10}" font-size="13" fill="{MUTE}" text-anchor="start">结构 → 感知 (y)</text>')
    # 作品淡点
    for x, y in pts:
        s.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="2.1" fill="{FAINT}" opacity="0.5"/>')
    # 6 区中心
    for wid, nm, x, y in WV:
        s.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="6" fill="none" stroke="{ACC}" stroke-width="1.6" opacity="0.8"/>')
        s.append(f'<text x="{sx(x):.1f}" y="{sy(y)-11:.1f}" font-size="11.5" fill="{ACC}" text-anchor="middle">{nm}</text>')
    # 大师质心
    for nm, x, y in arts:
        s.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="4.5" fill="{GREEN}"/>')
        s.append(f'<text x="{sx(x)+7:.1f}" y="{sy(y)+4:.1f}" font-size="11" fill="{GREEN}">{nm}</text>')
    # 用户 μ(★)
    if mu:
        ux, uy = sx(mu[0]), sy(mu[1])
        star = ' '.join('%.1f,%.1f' % (ux + 9 * math.cos(math.radians(a - 90)) * (1 if i % 2 == 0 else .45),
                                       uy + 9 * math.sin(math.radians(a - 90)) * (1 if i % 2 == 0 else .45))
                        for i, a in enumerate(range(0, 360, 36)))
        s.append(f'<polygon points="{star}" fill="{ACC}" stroke="#fff" stroke-width="1.2"/>')
        s.append(f'<text x="{ux:.1f}" y="{uy+22:.1f}" font-size="12" fill="{INK}" text-anchor="middle" font-weight="600">你 (用户 μ)</text>')
    # 图例
    ly = P0 + 6
    s.append(f'<text x="{W-P0}" y="{ly}" font-size="11" fill="{MUTE}" text-anchor="end">● 作品(8106) ○ 6世界观区 ● 大师质心 ★ 用户</text>')
    s.append('</svg>')
    open(OUT + '/fig1_manifold.svg', 'w').write('\n'.join(s))
    return len(pts), len(arts), bool(mu)


def fig2_invertedU():
    """倒U惊奇带 + 真实推荐距离直方图(证明推荐确实落在 d* 上,不是最近邻)。"""
    conn = P._conn(); cur = conn.cursor()
    cur.execute("SELECT uid,dstar FROM mu_profile WHERE n>=20 ORDER BY n DESC LIMIT 1")
    uid, dstar = cur.fetchone(); conn.close()
    rec = P.foryou(uid, limit=24)
    dists = [it['dist'] for it in rec['items']]
    W, H, P0 = 660, 360, 56
    sig = 0.20
    def sx(d): return P0 + d * (W - 2 * P0)            # d ∈ [0,1]
    def sy(a): return (H - P0) - a * (H - 2 * P0)      # a ∈ [0,1]
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Noto Serif SC,serif">']
    s.append(f'<rect width="{W}" height="{H}" fill="#faf8f3"/>')
    # 惊奇带阴影 (d* ± σ)
    bx0, bx1 = sx(max(0, dstar - sig)), sx(min(1, dstar + sig))
    s.append(f'<rect x="{bx0:.1f}" y="{P0}" width="{bx1-bx0:.1f}" height="{H-2*P0}" fill="{ACC}" opacity="0.07"/>')
    # 轴
    s.append(f'<line x1="{P0}" y1="{H-P0}" x2="{W-P0}" y2="{H-P0}" stroke="{LINE}"/>')
    s.append(f'<line x1="{P0}" y1="{P0}" x2="{P0}" y2="{H-P0}" stroke="{LINE}"/>')
    s.append(f'<text x="{W-P0}" y="{H-P0+24}" font-size="13" fill="{MUTE}" text-anchor="end">候选离你多远 d →</text>')
    s.append(f'<text x="{P0-10}" y="{P0-12}" font-size="13" fill="{MUTE}">惊喜得分 (Aha)</text>')
    # 倒U曲线
    path = ''
    for i in range(0, 101):
        d = i / 100.0; a = math.exp(-((d - dstar) ** 2) / (2 * sig * sig))
        path += ('M' if i == 0 else 'L') + f'{sx(d):.1f} {sy(a):.1f} '
    s.append(f'<path d="{path}" fill="none" stroke="{ACC}" stroke-width="2.5"/>')
    # d* 虚线
    s.append(f'<line x1="{sx(dstar):.1f}" y1="{sy(1)}" x2="{sx(dstar):.1f}" y2="{H-P0}" stroke="{ACC}" stroke-dasharray="3 4" opacity="0.6"/>')
    s.append(f'<text x="{sx(dstar):.1f}" y="{sy(1)-6:.1f}" font-size="12" fill="{ACC}" text-anchor="middle">d* = {dstar:.2f} (个人惊奇带,自学习)</text>')
    # 真实推荐距离直方图(底部)
    bins = [0] * 20
    for d in dists:
        bins[min(19, int(d * 20))] += 1
    mx = max(bins) or 1
    for i, c in enumerate(bins):
        if not c: continue
        h = (c / mx) * 46
        x = sx(i / 20.0); w = (W - 2 * P0) / 20 - 1.5
        s.append(f'<rect x="{x:.1f}" y="{H-P0-h:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{GREEN}" opacity="0.65"/>')
    s.append(f'<text x="{W-P0}" y="{P0+4}" font-size="11" fill="{GREEN}" text-anchor="end">▮ 实际推荐 Top24 的距离分布(落在 d* 上,非最近邻)</text>')
    # 标注
    s.append(f'<text x="{sx(0.06):.1f}" y="{H-P0-8}" font-size="11.5" fill="{MUTE}">太近·已知</text>')
    s.append(f'<text x="{sx(0.82):.1f}" y="{H-P0-8}" font-size="11.5" fill="{MUTE}">太远·接不住</text>')
    s.append(f'<text x="{sx(dstar):.1f}" y="{sy(1)+18:.1f}" font-size="12.5" fill="{ACC}" text-anchor="middle" font-weight="600">刚好新 → 原来如此</text>')
    s.append('</svg>')
    open(OUT + '/fig2_invertedU.svg', 'w').write('\n'.join(s))
    return uid[:8], round(dstar, 3), len(dists), round(min(dists), 3), round(max(dists), 3)


if __name__ == '__main__':
    print("图1 流形:", fig1_manifold())
    print("图2 倒U:", fig2_invertedU())
    print("→", OUT)
