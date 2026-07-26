#!/usr/bin/env python3
"""图(JIG)· 读画管线:画作图像 → VLM 多维解析 → 12 维审美坐标 → 知识图谱节点/审美流形。"""
OUT='/home/ubuntu/users/qiuyiwu/aha-art/docs/paper/figures/fig_pipeline.svg'
INK,MUTE,ACC,GREEN,GOLD,BLUE,LINE,PAPER='#1d1b18','#857d6f','#b0673a','#5a7d6f','#c98a1a','#5b7596','#ddd5c6','#faf8f3'
W,H=880,330
s=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Noto Sans SC,system-ui,sans-serif">']
s.append(f'<rect width="{W}" height="{H}" fill="{PAPER}"/>')
s.append('<defs><marker id="a" markerWidth="9" markerHeight="9" refX="6" refY="3" orient="auto"><path d="M0 0L6 3L0 6Z" fill="%s"/></marker></defs>'%ACC)
def box(x,y,w,h,c,r=10):
    s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="#fff" stroke="{c}" stroke-width="1.5"/>')
def txt(x,y,t,sz=12,c=INK,anc='start',w='400',f='Noto Sans SC,sans-serif'):
    s.append(f'<text x="{x}" y="{y}" font-size="{sz}" fill="{c}" text-anchor="{anc}" font-weight="{w}" font-family="{f}">{t}</text>')
def arrow(x1,y1,x2,y2):
    s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{ACC}" stroke-width="1.6" marker-end="url(#a)"/>')

# ① 画作图像
box(28,110,128,128,LINE)
# 简笔"画" 占位
s.append(f'<rect x="40" y="122" width="104" height="80" fill="#e9e0cf"/>')
s.append(f'<circle cx="70" cy="160" r="16" fill="#cdbf9c"/><rect x="92" y="150" width="44" height="40" fill="#b8c3b0"/>')
txt(92,228,'画作图像',12,MUTE,'middle')
txt(92,93,'① 输入',11,ACC,'middle','600','JetBrains Mono,monospace')

# ② VLM
box(196,118,150,112,ACC)
txt(271,150,'视觉语言模型',13.5,ACC,'middle','600','Noto Serif SC,serif')
txt(271,170,'(小米 MiMo)',11,MUTE,'middle')
txt(271,192,'沿锚定刻度逐幅解析',10.5,MUTE,'middle')
txt(271,208,'照相写实≈.1 睡莲≈.9',10,MUTE,'middle')
txt(271,103,'② 多维解析',11,ACC,'middle','600','JetBrains Mono,monospace')

# ③ 12 维坐标(三组条)
box(386,86,236,178,GREEN)
txt(504,103,'③ 12 维审美坐标',11,GREEN,'middle','600','JetBrains Mono,monospace')
groups=[('世界观 ·2',['再现↔表现 .80','结构↔感知 .70'],BLUE),
        ('绘画语言 ·7',['色彩 1.0  笔触 1.0','造型 .9  构图 .8  …'],GOLD),
        ('情绪 VAD ·3',['愉悦 .7  唤起 .8'],ACC)]
yy=120
for name,lines,c in groups:
    s.append(f'<rect x="398" y="{yy-12}" width="6" height="{12+15*len(lines)}" rx="3" fill="{c}"/>')
    txt(412,yy,name,11.5,c,'start','600')
    for i,ln in enumerate(lines):
        txt(412,yy+16+i*15,ln,10.5,MUTE,'start','400','JetBrains Mono,monospace')
    yy+=22+15*len(lines)

# ④ KG / 流形
box(662,110,190,128,INK,12)
txt(757,103,'④ 知识图谱 / 审美流形',11,ACC,'middle','600','JetBrains Mono,monospace')
# 小散点 + 一个高亮节点
import math
pts=[(700,150),(720,135),(745,160),(775,140),(800,168),(730,185),(770,200),(810,150),(690,175)]
for (px,py) in pts: s.append(f'<circle cx="{px}" cy="{py}" r="3" fill="{LINE}"/>')
s.append(f'<circle cx="757" cy="170" r="6" fill="{ACC}"/>')
txt(757,222,'2.2 万+ 作品 · 人画同空间',10.5,MUTE,'middle')

# 箭头
arrow(158,174,194,174); arrow(348,174,384,174); arrow(624,174,660,174)
# 标题
txt(28,40,'从一幅画到审美图谱:视觉语言模型驱动的多维语义解析',15,INK,'start','700','Noto Serif SC,serif')
txt(28,62,'每幅画被解析为 12 维可解释审美坐标(世界观2 + 语言7 + 情绪3),作品与用户同处一图;“风格是其它层的投影”。',11,MUTE,'start')
s.append('</svg>')
open(OUT,'w').write('\n'.join(s))
print('管线图已生成 →',OUT)
