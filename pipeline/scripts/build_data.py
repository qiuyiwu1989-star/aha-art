#!/usr/bin/env python3
"""把 artworks_raw.json + 人工策展(母题/感性点破/看点)+ 知识图谱,
合成最终 data/artworks.json 与 data/graph.json。"""
import json

raw = {w["slug"]: w for w in json.load(open("/home/ubuntu/users/qiuyiwu/aha-art-demo/data/artworks_raw.json"))}

# ── 人工策展层(母题 / 一句感性点破 / 看这里) ──
CURATION = {
 "paris-rainy": dict(themes=["都市","现代生活","雨","疏离","光影"],
   one="雨中的巴黎,人人共撑一伞却彼此不看——这是现代都市孤独的第一张肖像。",
   look="看那个被画框切掉一半的男人:卡耶博特用'随手一拍'的构图,让你也成了街上匆匆的一员。"),
 "grande-jatte": dict(themes=["都市休闲","秩序","光","现代生活","宁静"],
   one="一个慵懒的周日午后,被几百万个小点子,凝固成了永恒的纪念碑。",
   look="凑近看,没有线条,只有并排的纯色小点——后退几步,你的眼睛替修拉把它们调成了光。"),
 "vg-bedroom": dict(themes=["私密","孤独","色彩","居所","内心"],
   one="梵高把自己空荡的小屋画下来,只为说一件事:这里,是我的安宁。",
   look="墙是歪的、地是斜的——他故意让透视'不对',好让你感到一种紧绷的、属于他的安静。"),
 "waterlilies": dict(themes=["自然","水","光","宁静","沉思"],
   one="没有天、没有岸,只有水——莫奈把整个世界缩成一池倒影,请你沉下去。",
   look="找不到地平线,对吗?这正是他要的:让你失去坐标,只剩下光在水面上的呼吸。"),
 "haystacks": dict(themes=["自然","光","时间","田野","宁静"],
   one="同一堆麦垛,他画了一整组——因为他画的从来不是麦垛,是光,是一天里逝去的时间。",
   look="阴影其实不是灰的,是紫的、蓝的;莫奈教会我们:影子里也住满了颜色。"),
 "two-sisters": dict(themes=["人物","明媚","休闲","温情","光"],
   one="一个被阳光、毛线团和春天填满的瞬间——雷诺阿一生都在画这种纯粹的愉悦。",
   look="看背景怎么化成了一片斑斓的虚——他让人物清晰、世界融化,像记忆里最好的那种下午。"),
 "basket-apples": dict(themes=["静物","秩序","结构","日常","沉思"],
   one="一篮歪斜的苹果,桌沿对不上——塞尚故意'画错',因为他想画的是看的方式本身。",
   look="桌子的左右两边接不上线:他把不同角度的观看拼进同一幅画,这一步,直接通向了立体主义。"),
 "great-wave": dict(themes=["自然之力","海","动与静","崇高","东方"],
   one="一道要吞掉天空的浪,而远处的富士山,小得像浪尖的一滴静。",
   look="浪爪像手指一样抓向小船;北斋用一个程式化的瞬间,封存了大自然全部的力量与冷酷。"),
 "childs-bath": dict(themes=["温情","母与子","私密","日常","凝视"],
   one="一只手试水温,一只手扶着孩子——卡萨特把最寻常的母爱,画成了庄严。",
   look="高高的俯视角、压平的图案——这套'去掉纵深'的构图,她是从日本版画里学来的。"),
 "moulin-rouge": dict(themes=["夜生活","都市","人群","现代","疏离"],
   one="红磨坊的灯下,人挨着人,却各自孤独——劳特累克画夜场,不美化也不评判。",
   look="右下那张被煤气灯照成惨绿的脸,逼到了画框边缘:他让你直视夜生活不加修饰的真相。"),
 "el-greco-assump": dict(themes=["灵性","升腾","情感强度","宗教","扭曲的形"],
   one="身体被拉长、向上撕扯,色彩冷得发烫——四百年前,他就在画'情绪'本身。",
   look="所有人都被拉长、扭动,违背解剖——这种为情感而牺牲'正确'的胆量,三百年后才被现代画家重新拾起。"),
 "gauguin-day": dict(themes=["异域","神话","色彩","原始","灵性"],
   one="高更逃到塔希提,想找回文明之前的纯粹——画里那尊神,是他造的另一个世界。",
   look="看下方水中那几块纯粹的红、蓝、黄——他放弃了'真实的颜色',只为色彩本身的歌唱。"),
 "vg-selfportrait": dict(themes=["自我","凝视","色彩","内心","情感强度"],
   one="一圈圈短促的笔触像漩涡,绕着那双眼睛——梵高盯着自己,也盯着你。",
   look="背景不是平的,是一团涌动的笔触;他让整个空间都跟着他的神经一起震颤。"),
 "hiroshige": dict(themes=["自然","月","宁静","东方","诗意"],
   one="一枝红梅,斜斜划过夏夜的圆月——东方的留白,把'少'画成了'满'。",
   look="大片的空,只点一枝梅、一轮月;这种'以少胜多'的诗意,迷倒了整整一代欧洲画家。"),
 "monet-cliff": dict(themes=["自然","海","光","风","宁静"],
   one="海风把草吹成一个方向,两个小人站在崖边——莫奈画的是站在风里的那一刻。",
   look="海面不是蓝的,是被打碎的无数色块;眯起眼,它们才重新合成波光。"),
 "seurat-study": dict(themes=["自然","树","习作","光","宁静"],
   one="这是《大碗岛》的种子——修拉为那幅巨作画的小习作,你能看见方法正在成形。",
   look="还没铺满点彩,却已在试探光与影的分布;杰作不是凭空降临,是这样一步步长出来的。"),
 "renoir-lunch": dict(themes=["休闲","人物","明媚","温情","光"],
   one="塞纳河边餐馆的一顿午饭,阳光、酒杯和笑意——雷诺阿把'好好活着'画了下来。",
   look="光透过凉棚洒在桌布与脸上,斑斑驳驳;印象派最爱的,正是这种流动、不固定的光。"),
 "toulouse-jane": dict(themes=["夜生活","人物","现代","海报","疏离"],
   one="舞者简·阿弗丽尔,被劳特累克用一条果断的轮廓线,定格成了海报时代的偶像。",
   look="大块平涂、硬朗的边线、留白——这套海报语言直接学自日本版画,也定义了现代平面设计。"),
}

# ── 知识图谱:边(from, to, 类型, 为何相连)──
# 类型:influence 影响 / theme 同母题 / formal 形式呼应 / artist 同艺术家·过程 / movement 同流派·同代
EDGES = [
 # —— 日本主义的影响 ——
 ("great-wave","vg-bedroom","influence","梵高痴迷浮世绘:《大浪》的平涂色块与硬朗轮廓,正是《卧室》里大胆色彩与简化空间的来源。"),
 ("great-wave","moulin-rouge","influence","劳特累克的画面美学直接学自浮世绘——平面色块、果断的轮廓线,都来自《大浪》这类版画。"),
 ("great-wave","gauguin-day","influence","高更的平涂色块与装饰性轮廓,同样吸收了日本版画的语言。"),
 ("great-wave","toulouse-jane","influence","《简·阿弗丽尔》海报里的平面与轮廓,延续着浮世绘对劳特累克的影响。"),
 ("hiroshige","waterlilies","influence","莫奈收藏了大量广重与北斋的版画;他铺满画面、取消地平线的水面,呼应着浮世绘的平面构图。"),
 ("hiroshige","childs-bath","influence","卡萨特从日本版画学来高视角与压平的空间——《沐浴》俯视的构图正是这种影响。"),
 # —— 浮世绘(同流派)——
 ("great-wave","hiroshige","movement","同属浮世绘——日本江户时代的木刻版画,描绘'浮世'的风景与人生。"),
 # —— 印象派(同艺术家 / 同流派)——
 ("waterlilies","haystacks","artist","同是莫奈——他用成组的画,追逐同一对象在不同光线下的瞬间。"),
 ("waterlilies","monet-cliff","artist","同是莫奈——从海崖到睡莲,他一生都在追光。"),
 ("haystacks","monet-cliff","artist","同是莫奈的户外之作,都是对光与瞬间的执着记录。"),
 ("two-sisters","renoir-lunch","artist","同是雷诺阿——印象派里最擅长画明媚、温暖、欢愉时刻的人。"),
 ("monet-cliff","two-sisters","movement","同属印象派——捕捉户外光线与现代生活的瞬间。"),
 ("paris-rainy","renoir-lunch","movement","卡耶博特既是印象派画家,也是他们的赞助人;与雷诺阿同属这场捕捉现代巴黎生活的运动。"),
 # —— 现代休闲(同母题)——
 ("paris-rainy","grande-jatte","theme","两幅都画'现代巴黎人的闲暇',相隔七年——卡耶博特用写实的雨天街道,修拉用点彩的午后岛屿:同一主题,两种手法。"),
 ("grande-jatte","renoir-lunch","theme","都是河边/岛上的休闲时光——印象派一代对'现代生活'的共同迷恋。"),
 # —— 新印象主义的诞生(影响)——
 ("haystacks","grande-jatte","influence","修拉把印象派对光的直觉,升级成一套科学的点彩方法——新印象主义由此诞生。"),
 ("seurat-study","grande-jatte","artist","这就是《大碗岛》的种子——修拉为那幅巨作所画的习作,你能看见方法正在成形。"),
 ("seurat-study","monet-cliff","theme","都是对户外、光与自然瞬间的观察,印象派一代共同的功课。"),
 # —— 后印象派(同流派)——
 ("vg-bedroom","gauguin-day","influence","梵高与高更1888年在阿尔同住两月,亦师亦敌;两人都把色彩从'描摹'推向'表达'。"),
 ("vg-selfportrait","vg-bedroom","artist","同是梵高、同一时期——你能在自画像与卧室里认出同一双手、同一种躁动的笔触。"),
 ("basket-apples","grande-jatte","movement","塞尚、修拉、高更、梵高同属后印象派——都在印象派之后,寻找比'瞬间光线'更恒久的结构与情感。"),
 ("basket-apples","gauguin-day","movement","同属后印象派——一个用结构、一个用色彩与象征,各自越过印象派往前走。"),
 ("basket-apples","vg-bedroom","movement","同属后印象派——塞尚求'形'的恒久,梵高求'情'的炽烈。"),
 # —— 埃尔·格列柯:跨越四百年的桥 ——
 ("el-greco-assump","basket-apples","influence","塞尚推崇埃尔·格列柯——这位16世纪画家拉长的形体与结构性的色彩,启发了塞尚对'形'的重新构造。"),
 ("el-greco-assump","vg-selfportrait","theme","相隔三百年的同一种东西:灵性的、情感过载的强度,与不安分、被拉长扭曲的形。"),
 # —— 水与自然之力(跨文化同母题)——
 ("great-wave","monet-cliff","theme","同样面对海与自然之力,东西方各自的答案:北斋程式化的巨浪,莫奈瞬间的光色。"),
 ("great-wave","waterlilies","theme","同是'水'——一个把它画成吞天的力量,一个把它画成无边的宁静。"),
 ("hiroshige","haystacks","theme","都把'自然中一个寻常的片刻'郑重对待:广重的夏月红梅,莫奈的麦垛黄昏。"),
 # —— 夜与都市中的人(同母题)——
 ("moulin-rouge","toulouse-jane","artist","同是劳特累克、同一个蒙马特的夜——他画夜生活里的人,不美化、也不评判。"),
 ("moulin-rouge","paris-rainy","theme","同是现代都市里的人——卡耶博特画雨中擦肩的疏离,劳特累克画夜场人群里的孤独。"),
 # —— 温柔的注视(同母题)——
 ("childs-bath","two-sisters","theme","同是温柔的注视——卡萨特的母与子,雷诺阿的姐妹,印象派里少见的亲密。"),
]

TYPE_LABEL = {"influence":"影响","theme":"同母题","formal":"形式呼应","artist":"同艺术家","movement":"同流派"}

# 组装作品
works = []
for slug, w in raw.items():
    c = CURATION.get(slug, {})
    works.append({
        "slug": slug, "title": w["title"], "artist": w["artist"], "date": w["date"],
        "year": w.get("year"), "medium": w.get("medium"), "origin": w.get("origin"),
        "image": w["image"], "lqip": w.get("lqip"), "alt": w.get("alt"),
        "themes": c.get("themes", []), "oneLiner": c.get("one",""), "look": c.get("look",""),
    })

slugs = {w["slug"] for w in works}
for a,b,t,_ in EDGES:
    assert a in slugs and b in slugs, f"edge endpoint missing: {a}->{b}"

graph = {
  "typeLabels": TYPE_LABEL,
  "edges": [{"a":a,"b":b,"type":t,"why":why} for (a,b,t,why) in EDGES],
}

json.dump(works, open("/home/ubuntu/users/qiuyiwu/aha-art-demo/data/artworks.json","w"), ensure_ascii=False, indent=2)
json.dump(graph, open("/home/ubuntu/users/qiuyiwu/aha-art-demo/data/graph.json","w"), ensure_ascii=False, indent=2)

# 连通性自检
from collections import defaultdict, deque
adj=defaultdict(set)
for e in graph["edges"]:
    adj[e["a"]].add(e["b"]); adj[e["b"]].add(e["a"])
start=next(iter(slugs)); seen={start}; q=deque([start])
while q:
    for n in adj[q.popleft()]:
        if n not in seen: seen.add(n); q.append(n)
print(f"works={len(works)} edges={len(graph['edges'])} connected={len(seen)}/{len(slugs)}")
mind=min(len(adj[s]) for s in slugs); print("min degree =", mind, "(每个作品至少这么多扇门)")
print("orphans:", [s for s in slugs if not adj[s]])
