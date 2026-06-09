#!/usr/bin/env python3
# 导出两份"待团队补真实语料"的清单(CSV, 带 BOM 便于 Excel 直接打开)
#   ① exports/缺why关系清单.csv  —— 394 条真实谱系关系缺"出处理由";附两端 born/def 供照抄/改写
#   ② exports/艺术家作品待补图清单.csv —— 每位艺术家的代表作,留空"图片URL/来源"列待填(铁律:只填可核实真图)
# 一切坚持 真实、可追溯、不编造:理由必须能在某端 born/def 里找到依据;图片必须是真作。
import json, os, csv

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(HERE, 'exports'); os.makedirs(OUT, exist_ok=True)
gal  = json.load(open(os.path.join(HERE,'data','kg_galaxy.json'), encoding='utf-8'))
sty  = json.load(open(os.path.join(HERE,'data','kg_style.json'),  encoding='utf-8'))
art  = json.load(open(os.path.join(HERE,'data','kg_artists.json'),encoding='utf-8')).get('artists',{})

byId = {n['id']:n for n in sty['nodes']}
def cn(i):   return byId.get(i,{}).get('cn', i)
def born(i): return (byId.get(i,{}).get('lore',{}) or {}).get('born','') or ''
def deff(i): return byId.get(i,{}).get('def','') or ''
KIND = {'parent':'承自','influence':'影响','against':'对抗'}

# ① 缺 why 的关系
miss = [e for e in gal['edges'] if not e.get('w')]
miss.sort(key=lambda e:(KIND.get(e['k'],e['k']), cn(e['s'])))
p1 = os.path.join(OUT,'缺why关系清单.csv')
with open(p1,'w',newline='',encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['序号','源风格','关系','对象风格','置信','✍️待填:一句出处理由(必须真实/可在下两栏找到依据)',
                '源·born(背景)','源·def(定义)','对象·born(背景)','对象·def(定义)','源id','对象id'])
    for k,e in enumerate(miss,1):
        w.writerow([k, cn(e['s']), KIND.get(e['k'],e['k']), cn(e['t']), e.get('c',''),
                    '', born(e['s']), deff(e['s']), born(e['t']), deff(e['t']), e['s'], e['t']])

# ② 艺术家作品待补图清单
rows=[]
for aid,a in art.items():
    works = a.get('works') or []
    if not works:
        rows.append([aid, a.get('cn',''), a.get('region',''), a.get('headline',''), '(暂无代表作记录)','', '', ''])
        continue
    for wk in works:
        rows.append([aid, a.get('cn',''), a.get('region',''), a.get('headline',''),
                     wk.get('t',''), wk.get('year',''), '', ''])
rows.sort(key=lambda r:(r[2], r[1]))
p2 = os.path.join(OUT,'艺术家作品待补图清单.csv')
with open(p2,'w',newline='',encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['艺术家id','艺术家','东西','一句定位','代表作','年代',
                '✍️待填:图片URL(铁律=可核实真图,如美术馆/维基公共领域)','✍️待填:来源/版权说明'])
    for r in rows: w.writerow(r)

# 说明
readme = os.path.join(OUT,'README.txt')
open(readme,'w',encoding='utf-8').write(
 '这两份清单用于"会发光的艺术史"补真实语料,做完即可在星图里点亮。\n\n'
 '① 缺why关系清单.csv —— 共 %d 条真实谱系关系还没有"出处理由"(诚实留空)。\n'
 '   请在「待填」列写一句话,说明这条 承自/影响/对抗 的依据。\n'
 '   右侧已附两端的 born/def 原文,理由应当能在其中找到根据,不要编造。\n\n'
 '② 艺术家作品待补图清单.csv —— 共 %d 行,每位艺术家的代表作。\n'
 '   请填「图片URL」与「来源」。铁律:只填可核实的真作图(美术馆官网/维基公共领域等),\n'
 '   宁可留空,不要放生成图或来路不明的图。填好后这些作品会作为第四层"作品宇宙"亮起。\n'
 % (len(miss), len(rows)))

print('① 缺why关系清单.csv :', len(miss), '条')
print('② 艺术家作品待补图清单.csv :', len(rows), '行 (艺术家', len(art),')')
print('输出目录:', OUT)
