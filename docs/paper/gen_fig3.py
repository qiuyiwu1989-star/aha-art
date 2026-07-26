#!/usr/bin/env python3
"""图3 · 系统架构:四种逛法 → 三张信号表 → 三层时间尺度 → 推荐。手绘式 SVG。"""
OUT = '/home/ubuntu/users/qiuyiwu/aha-art/docs/paper/figures/fig3_architecture.svg'
INK, MUTE, ACC, GREEN, GOLD, BLUE, LINE, PAPER = '#1d1b18', '#857d6f', '#b0673a', '#5a7d6f', '#c98a1a', '#5b7596', '#ddd5c6', '#faf8f3'
W, H = 880, 520
s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Noto Sans SC,system-ui,sans-serif">']
s.append(f'<rect width="{W}" height="{H}" fill="{PAPER}"/>')
s.append('<defs><marker id="ar" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0 0L6 3L0 6Z" fill="%s"/></marker></defs>' % MUTE)

def box(x, y, w, h, title, sub, color, tcol='#1d1b18', r=10):
    s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="#fff" stroke="{color}" stroke-width="1.5"/>')
    s.append(f'<text x="{x+w/2}" y="{y+22}" font-size="13.5" font-weight="600" fill="{tcol}" text-anchor="middle" font-family="Noto Serif SC,serif">{title}</text>')
    if sub:
        for i, ln in enumerate(sub):
            s.append(f'<text x="{x+w/2}" y="{y+40+i*15}" font-size="10.5" fill="{MUTE}" text-anchor="middle">{ln}</text>')

def arrow(x1, y1, x2, y2):
    s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{MUTE}" stroke-width="1.4" marker-end="url(#ar)"/>')

s.append(f'<text x="28" y="34" font-size="15" font-weight="700" fill="{INK}" font-family="Noto Serif SC,serif">从四种「逛法」到下一帧</text>')
# 列标题
for cx, t in [(120, '① 四种逛法 / 模态'), (375, '② 三张信号表'), (640, '③ 三层时间尺度'), (640, '')]:
    if t: s.append(f'<text x="{cx}" y="62" font-size="11" fill="{ACC}" text-anchor="middle" font-family="JetBrains Mono,monospace" letter-spacing="1">{t}</text>')
s.append(f'<text x="800" y="62" font-size="11" fill="{ACC}" text-anchor="middle" font-family="JetBrains Mono,monospace">④ 推荐</text>')

# ① 四逛法
modes = [('看展', ['浏览·停留·心动', '收藏·跳过']), ('相框电台', ['被动轮播·双击', '展示≠观看']),
         ('语音心愿', ['ASR→LLM 解析', '会处理否定']), ('生成', ['意图编译器', '主动要的方向'])]
for i, (t, sub) in enumerate(modes):
    box(30, 78 + i*102, 180, 84, t, sub, GREEN)
# ② 三表
tables = [('mu_event', ['行为 revealed', 'like/dwell/skip/expose']), ('mu_wish', ['陈述 stated', 'text/av/vv/region']),
          ('mu_generation', ['创作'])]
ty = [88, 230, 350]
for i, (t, sub) in enumerate(tables):
    box(290, ty[i], 170, 70 if len(sub) > 1 else 56, t, sub, BLUE)
# 箭头 ①→②
for i in range(4):
    arrow(210, 120 + i*102, 290, [123, 265, 265, 385][i] if i < 4 else 265)
# 更明确:看展+相框→mu_event;语音→mu_wish;生成→mu_generation
# ③ 三层
layers = [('此刻心情', ['≤30min', '→ 相框 next_frame'], ACC), ('近来意图', ['7天半衰期', '→ 为你推荐 foryou'], GOLD),
          ('长期身份', ['只看行为', '→ 审美档案 μ'], GREEN)]
for i, (t, sub, c) in enumerate(layers):
    box(560, 88 + i*120, 190, 92, t, sub, c)
# 箭头 ②→③
arrow(460, 123, 560, 134)   # event→此刻
arrow(460, 265, 560, 254)   # wish→近来
arrow(460, 265, 560, 330)   # event→身份(行为)
arrow(460, 385, 560, 360)   # gen→身份/近来
# ④ 推荐核心
box(778, 200, 92, 120, '打分', ['熟悉↔惊喜', 'rel=(1−ex)·sim', '+ ex·aha', '倒U·d*'], ACC)
for i in range(3):
    arrow(750, 134 + i*120, 778, 235 + (i-1)*30)
# 底部注
s.append(f'<text x="28" y="{H-16}" font-size="10.5" fill="{MUTE}" font-family="JetBrains Mono,monospace">说的话调「给你看什么」(stated→此刻/近来) · 做的事定「你是谁」(revealed→身份 μ);两者结合、互不覆盖。</text>')
s.append('</svg>')
open(OUT, 'w').write('\n'.join(s))
print('图3 已生成 →', OUT)
