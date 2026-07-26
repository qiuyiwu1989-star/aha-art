#!/usr/bin/env python3
# 回填 artists.name_cn / name_en,使中英文成对;默认中文(API COALESCE(name_cn,name_en))。
# CN[] 对齐 /tmp/need_cn.json(522,补中文);EN[] 对齐 /tmp/need_en.json(326,补英文)。
# None = 跳过(非人名:风格/院体/牌组)。先备份旧值,事务内 UPDATE,可回滚。
import json, os, sys, psycopg2
from psycopg2.extras import RealDictCursor

CN = [  # EN -> 中文 (index aligned to need_cn.json, 522)
"阿龙·西斯金德","阿卜杜拉·苏里奥苏布罗托","阿基莱·多尔西","亚当·巴尔塔图","阿德加·扬克斯","阿道夫·蒙蒂塞利","阿德·莱因哈特","阿德里安·范·德·维恩","阿古斯丁·卡德纳斯","阿克塞利·加伦-卡勒拉",
"阿尔贝·贝努阿","阿尔伯特·朱利叶斯·奥尔森","阿尔贝托·贾科梅蒂","阿尔贝托·希罗内利亚","阿尔布雷希特·亚当","亚历杭德罗·奥夫雷贡","亚历山大·盖雷姆斯基","阿列克谢·安特罗波夫","阿列克谢·伊万诺维奇·科尔祖欣","亚历山大·巴日别乌克-梅利基扬",
"亚历山大·博根","亚历山大·博戈相","亚历山大·克拉罗","亚历山大·伊斯特拉蒂","亚历山德鲁·丘库伦库","阿列克西斯·格里琴科","阿尔弗雷德·克鲁帕","阿尔弗雷德·马奈西耶","阿尔弗雷多·安德森","阿尔弗雷德·帕森斯",
"爱丽丝·拉洪","阿利娜·沙波奇尼科夫","阿拉·霍尔斯卡","阿隆佐·查佩尔","阿纳托利·帕皮扬","安德烈亚斯·阿亨巴赫","安德烈·迪努瓦耶·德·塞贡扎克","安德烈·朗斯科伊","安德烈斯·德·圣玛丽亚","安德烈·阿拉赫韦尔多夫",
"安杰伊·弗鲁布莱夫斯基","安杰洛·佐弗利","安妮·布里格曼","安妮·瑞安","安东尼奥·达席尔瓦·波尔图","安东尼奥·卡内罗","安东尼奥·德·拉·甘达拉","安东尼奥·保莱蒂","安东·米托夫","阿波利纳里·戈拉夫斯基",
"阿拉·别卡良","阿里斯蒂德·马约尔","阿尔卡季·雷洛夫","阿曼多·蒙塔内尔·瓦尔杜埃萨","阿尔芒·瓦扬库尔","阿尔沙克·费特瓦吉扬","阿瑟·皮纳吉扬","阿瑟·韦罗纳","阿斯格里穆尔·约恩松","奥古斯特·埃杜阿尔",
"奥古斯特·罗丹","奥斯汀·奥斯曼·斯佩尔","巴布肯·科洛兹扬","巴赫曼·莫哈塞斯","巴兹尔·比蒂","贝赫贾特·萨德尔","贝拉·卡达尔","贝蒂·帕森斯","布林基·帕勒莫","博莱斯拉斯·别加斯",
"鲍里斯·沙茨","博若基·玛丽亚","布拉塞","布莱斯·马登","布里翁·吉辛","布鲁诺·卡诺瓦","卡米耶·布里昂","卡米耶·克洛岱尔","卡尔·霍尔瑟","卡洛斯·博特略",
"卡洛斯·萨恩斯·德·特哈达","查尔斯·阿塔米扬","查尔斯·吉本斯","查尔斯·赫尔曼斯","查尔斯·拉皮克","查尔斯·拉瓦尔","查尔斯·莫兰","沙尔莱","克里斯蒂安·奥古斯特·洛伦岑","朱德群",
"克拉拉·萨瑟恩","克劳德·卡恩","克劳德·乔治","科莱特·波普·赫尔德纳","康斯坦丁·阿尔塔基诺","康斯坦丁·布朗库西","康斯坦丁·丹尼尔·罗森塔尔","西里尔·鲍尔","赛·托姆布雷","达恩·勒梅尔",
"达多","丹·克里斯滕森","埃林·达尼埃尔松-甘博吉","大卫·贝茨","大卫·戴维斯","大卫·斯科特","大卫·史密斯","迪米特里·帕丘雷亚","多布里·多布列夫","多尔菲·特罗斯特",
"多梅尼科·菲亚塞拉","多梅尼科·尼奥利","多拉·博内娃","阿特尔博士","阿尔贝特·埃德尔费尔特","埃德加·沙欣","爱德华·德·比埃夫","爱德华·里乌","爱德华·伊萨别基扬","爱德华·冯·格吕茨纳",
"埃德瓦·魏埃","爱德华·科比特","爱德华·拉德尔","爱德华·沃兹沃思","爱德华·韦斯顿","埃德温·亨利·兰西尔","叶菲姆·沃尔科夫","伊莱恩·德·库宁","埃米尔·普里斯·达文","埃米尔·菲拉",
"埃米莉·沙尔米","埃马努埃尔·扎伊里斯","安德烈·巴林特","埃罗尔·阿克亚瓦什","埃斯特万·维森特","埃特尔·阿德南","埃塞尔·卡里克","艾蒂安·哈伊杜","欧仁·扬松","欧仁·勒罗瓦",
"欧仁·冯·盖拉德","法比奥·德·桑克蒂斯","费利克斯·路易·勒利耶","费迪南德·格奥尔格·瓦尔德米勒","费尔南·孔布","费尔南·克诺普夫","费尔南·勒杜克","费尔南多·加西亚·彭塞","菲利波·奇法列洛","福里斯特·贝斯",
"弗朗西斯科·塞拉·安德烈斯","弗朗索瓦·阿纳尔","弗朗索瓦·勒穆瓦纳","弗兰克·鲍林","弗兰克·奥梅拉","弗雷德里克·索默","弗雷德·威廉姆斯","弗里德尔·楚巴斯","弗里登斯赖希·洪德特瓦塞尔","费奥多尔·索尔采夫",
"加里·拉格","热纳维耶芙·阿斯","乔治·奥尔特","乔治·哈维","乔治·亨利","乔治·菲利普·赖纳格尔","乔治·里布蒙-德塞涅","格奥尔基·科瓦切夫","格奥尔基·马舍夫","格奥尔格·保利",
"格奥尔格·塔佩特","热拉尔·施奈德","杰拉德·范·洪特霍斯特","杰罗拉莫·因杜诺","盖奥尔基·彼得拉什库","贾科莫·曼祖","吉莉安·艾尔斯","乔瓦尼·巴蒂斯塔·高利","乔瓦尼·保罗·帕尼尼","朱塞佩·阿巴蒂",
"戈哈尔·费尔曼扬","格里戈里·戈尔德施泰因","格雷古瓦尔·米雄兹","格里戈里·米亚索耶多夫","圭多·维亚罗","吉蒂·诺文","京特·弗尔格","古斯塔夫·阿道夫·莫萨","古斯塔沃·福皮亚尼","佩卡·哈洛宁",
"汉内洛蕾·巴伦","汉斯·安·恩德","汉斯·贝尔默","汉斯·海森","哈丽特·巴克尔","哈里·费伦·吉布","哈塞尔·史密斯","海因里希·布尔克尔","海伦·奥古斯塔·汉堡格","海伦·达姆",
"海伦·弗兰肯塔勒","亨利·卡塔尔吉","恩里克·波桑","亨利·阿瑟·麦卡德尔","亨里克·贝尔莱维","亨里克·罗达科夫斯基","亨利·摩尔","亨利·范德维尔德","赫伯特·古斯塔夫·施马尔茨","赫拉克勒斯·塞格尔斯",
"赫尔曼·奥托马尔·赫尔佐格","埃尔韦·泰勒马克","海伍德·哈迪","霍默·沃森","霍勒斯·特雷纳里","霍夫汉内斯·扎尔达良","霍夫塞普·普什曼","霍华德·霍奇金","胡戈·米利希","于盖特·阿瑟·贝特朗",
"伊恩·本特","易卜拉欣·查勒","易卜拉欣·萨拉希","伊戈尔·格拉巴里","伊尔莎·多兰德","约阿尼斯·阿尔塔穆拉斯","伊波利托·卡菲","伊萨克·伊斯拉埃尔斯","伊什特万·法尔卡什","伊什特万·纳吉",
"伊万·格罗哈尔","伊万·梅什特罗维奇","伊万·米列夫","伊万·姆尔克维奇卡","伊万·尼基京","伊万·鲁特科维奇","伊万·特沃罗日尼科夫","伊万·扎多罗日内","杰克·布什","杰克·特沃尔科夫",
"雅各芭·范·海姆斯凯克","杰奎琳·希克","雅克·比斯","雅克·埃罗尔德","詹姆斯·阿彻","詹姆斯·布鲁克斯","詹姆斯·坎贝尔·诺布尔","简·弗兰克","简·萨瑟兰","扬·曼克斯",
"亚诺什·托尔尼艾","埃罗·耶尔内费尔特","杰伊·德费奥","让·亚历山德鲁·斯特里亚迪","让·阿尔普","让-巴蒂斯特·卡尔波","让-巴蒂斯特·皮加勒","让-克劳德·西尔伯曼","让·勒莫阿尔","让·梅萨吉耶",
"让-保罗·里奥佩勒","让-勒内·巴赞","杰里米·亨德森","吉米·恩斯特","琼·布劳","琼·布鲁尔","琼·斯奈德","华金·阿格拉索特","华金·多明格斯·贝克尔","华金·索罗拉",
"乔·古德","约翰·巴普蒂斯特·克拉罗","约翰内斯·斯韦因松·恰瓦尔","约翰·格奥尔格·平泽尔","约翰·阿尔图恩","约翰·鲍尔","约翰·凯奇","约翰·张伯伦","约翰·邓肯","约翰·费伦",
"约翰·哈特菲尔德","约翰·亨德森","约翰·霍伊兰","约翰·穆阿凡盖乔","约翰·罗德姆·斯宾塞·斯坦霍普","约翰·拉斯金","豪尔赫·卡斯蒂略","何塞·坎佩切","若泽·埃斯卡达","约瑟夫·恰佩克",
"约瑟夫·克里胡贝尔","约瑟夫·希马","何塞·格雷罗","何塞·卢桑","若泽·马尔霍亚","约瑟夫·康奈尔","约瑟夫·乌尔巴尼亚","乔伊·赫斯特","约瑟夫·赫尔蒙斯基","约瑟夫·梅霍费尔",
"约瑟夫·潘凯维奇","胡安·范·德·哈门","朱尔斯·奥利茨基","朱尔·帕散","朱莉娅·玛格丽特·卡梅伦","朱利安·阿什顿","尤利安·法瓦特","胡里奥·波马尔","胡里奥·罗梅罗·德·托雷斯","尤里安·波尔",
"尤里安·范·斯特雷克","卡尔波·特罗希缅科","凯绥·珂勒惠支","中村一夫","冈田谦三","基蒂·朗格·谢兰","康斯坦丁诺斯·马莱亚斯","康斯坦丁诺斯·沃拉纳基斯","康斯坦丁·瓦西里耶夫","康斯坦丁·尤翁",
"弗里达·哈里斯夫人","拉约什·蒂哈尼","拉里·里弗斯","拉里·佐克斯","拉斯洛·梅德尼安斯基","李·克拉斯纳","莱昂·阿瑟·图通吉扬","列昂尼德·谢伊卡","利奥波德·罗贝尔","利奥·斯蒂尔",
"莉莉·埃尔伯","路易丝·内维尔森","路易·让莫","路易·菲利普·克雷潘","路德维希·贝梅尔曼斯","玛吉·劳布瑟","马格努斯·恩克尔","马娜·帕尔普洛娃","曼努切赫尔·叶克塔伊","曼努埃尔·阿尔瓦雷斯·布拉沃",
"曼努埃尔·卡尔加莱罗","曼努埃尔·罗德里格斯·德·古斯曼","马塞尔·巴尔博","马塞尔·马里安","玛丽·沃罗比耶娃(玛雷夫娜)","玛格丽塔·斯特里安","马里亚诺·本柳雷","玛丽·洛朗森","玛丽-泰蕾兹·奥弗雷","马里诺·马里尼",
"马里奥·埃洛伊","马里奥·普拉西诺斯","玛乔丽·阿克·菲利普斯","马克·迪·苏韦罗","马克·罗斯科","马克·托比","马滕·埃斯基尔·温格","马丁·本卡","马丁·奇里诺","马丁·里科",
"马蒂尔·朗斯多夫","马鲁哈·马略","玛丽·约瑟芬·沃尔特斯","马特伊·斯特尔嫩","马蒂亚斯·劳伦茨·格拉夫","莫里斯·布瓦泰尔","莫里斯·邦帕尔","莫里斯·布劳恩","莫里斯·埃斯特夫","莫里斯·塔巴尔",
"马克斯·克林格尔","马克斯·奥本海默","梅纳德·迪克森","梅达尔多·罗索","梅尔西奥·德·洪德库特","梅雷特·奥本海姆","米歇尔·基科因","米格尔·卡夫雷拉","米赫里·穆什菲克","米卡洛尤斯·丘尔利奥尼斯",
"米库拉什·梅德克","米尔德里德·安妮·巴特勒","米尔顿·雷斯尼克","米米·帕朗","莫德·刘易斯","莫迪凯·阿尔东","米哈伊洛·博伊丘克","米科拉·穆拉什科","尼古拉·亚罗申科","娜杰日达·彼得罗维奇",
"纳西斯·迪亚兹","娜塔莉亚·杜米特雷斯科","小纳撒尼尔·霍恩","内马尼亚·武奇科维奇","尼古拉斯·卡罗内","尼古拉·德米特里耶维奇·库兹涅佐夫","尼古拉·马蒂诺斯基","尼古拉斯·利特拉斯","妮娜·阿尔博雷","诺曼·布卢姆",
"奥克塔夫·安格卢察","奥列克萨·诺瓦基夫斯基","亚历山大·阿尔希片科","奥梅尔·穆亚季奇","奥龙佐·维托·加斯帕罗","奥斯瓦尔德·阿亨巴赫","奥东·弗里兹","奥托·康斯坦丁","奥托内·罗萨伊","帕诺斯·特尔列梅兹扬",
"帕斯夸莱·切洛米","帕特·利普斯基","保罗·阿克曼","保罗·加瓦尔尼","保罗·马蒂奥普洛斯","保罗·帕温","保罗·韦尔纳","帕维尔·费多托夫","佩德罗·卡拉佩斯","佩里克利斯·潘塔齐斯",
"佩里克利斯·维赞蒂奥斯","珀尔·法恩","彼得·布萨","彼得·尼古拉·阿尔博","老彼得罗·霍洛德内","彼得罗斯·马拉扬","菲利普·哈尔斯曼","菲利普·奥托·龙格","皮埃尔·莫利尼耶","彼得·科德",
"彼得·文宁","彼得罗·拉扎里","平丘斯·克雷姆涅","波利赫罗尼斯·伦贝西斯","普鲁登斯·休厄德","雷蒙多·马德拉索","拉尔夫·法萨内拉","拉尔夫·赫德利","拉尔夫·罗森博格","拉乌尔·于巴克",
"雷·帕克","雷克纳·诺萨尔","鲁本·纳基安","小理查德·卡顿·伍德维尔","理查德·杰克","理查兹·鲁本","老罗伯特·德尼罗","罗伯特·尼克尔","罗伯特·威廉·巴斯","罗杰·弗莱",
"罗尼·兰菲尔德","罗萨里奥·魏斯·索里利亚","罗斯玛丽·贝克","鲁本斯·桑托罗","鲁道夫·贝尔","鲁道夫·朗","鲁菲诺·塔马约","梅原龙三郎","蒂科·萨利宁","山姆·弗朗西斯",
"山姆·吉列姆","塞缪尔·范·霍赫斯特拉滕","塞缪尔·莫尔斯","塞缪尔·施瓦茨","常玉","萨拉·珀塞尔","沙鲁纳斯·绍卡","萨塔尔·巴赫卢尔扎德","萨韦里奥·德拉·加塔","谢德拉克·阿拉克良",
"谢尔盖·帕拉杰诺夫","塞韦尔·布拉达","西尔维斯特·谢德林","西梅翁·韦尔科夫","西蒙·乌沙科夫","西拉克·斯基特尼克","威廉·拉塞尔·弗林特爵士","索尼娅·德劳内","斯坦利·博克瑟","斯蒂芬·米勒",
"特奥多尔·哈尔希亚","塔利亚·弗洛拉-卡拉维亚",None,"西奥多·范·蒂尔登","特奥多尔·阿曼","特奥多尔·利奥波德·韦勒","西奥多罗斯·斯塔莫斯","托马斯·波洛克·安舒茨","托马斯·史密斯","汤姆·斯科特",
"陈文谨","山崎鹤子","乌尔弗特·维尔克","瓦迪姆·梅勒","瓦赫拉姆·盖费吉扬","凡妮莎·贝尔","瓦尔坦·马霍基扬","瓦西列·波佩斯库","瓦西里·克里切夫斯基","薇拉·涅德科娃",
"维克托·梅雷莱斯","维克托·帕尔莫夫","维克托·塞夫朗克斯","弗拉迪·基巴尔奇奇·鲁萨科夫","弗谢沃洛德·马克西莫维奇","维陶塔斯·卡修利斯","维尔纳·贝格","维尔纳·派纳","威尔·巴尼特","威廉·范·阿尔斯特",
"威廉·范·斯瓦嫩堡","威廉·康登","威廉·亨利·赫德尔","威廉·莫里斯","威廉·萨罗扬","威廉·谢耶","威廉·西德尼·库珀","威廉·特纳","威利·施洛巴赫","弗沃齐米日·扎克热夫斯基",
"尤里·兹洛特尼科夫","扎卡尔·扎卡良",
]

EN = [  # 中文 -> EN (index aligned to need_en.json, 326)
"Ding Yilin","Ding Fang","Ding Liren","Ding Hong","Albrecht Dürer","Mamat Ayit",None,"Qiu Ying","Ren Bonian","He Duoling",
"He Daqiao","He Kongde","He Shuhai","He Hongzhou","Yu Ben","Anonymous","Anonymous (Contemporary)","Hou Yimin","Hou Shanhu","Yu Yunjie",
"Yu Xiaofu","Georges Seurat","Ni Zan","Ni Yide","Bada Shanren","Lan Chengbing","Guan Zilan","Guan Liang","Ran Maoqin","Feng Fasi",
"Feng Gangbai","Leng Jun","Jan van Eyck","Liu Shiguo","Liu Yaming","Liu Kongxi","Liu Yuyi","Liu Xiaodong","Liu Haisu","Liu Xun",
"Liu Ye","Antoine Watteau","Wei Tianlin","Situ Qiao","Lü Sibai","Wu Yunhua","Wu Zuoren","Wu Guanzhong","Wu Dayu","Wu Zhen",
"Zhou Junhua","Zhou Shuqiao","Zhou Zheng","Hazi Ahmat","Tang Yihe","Tang Weimin","Tang Yin","Yu Hong","Paul Cézanne","Moke",
"Tomus","Diego Velázquez","Jiang Guofang","Jiang Jianzhong","Sun Weimin","Sun Xiangyang","Sun Jingbo","Sun Hao","Sun Man","Sun Tao",
"Andrei Sklyarenko","Song Huimin","Song Xianzhen","Gong Lilong","Shang Dezhou","Shang Yang","You Jindong","Qi Mengguang","Yue Minjun","Cui Ji",
"Cui Guoqiang","Baldassare Tommaso Peruzzi","François Boucher","Egon Schiele","Chang Shuhong","Chang Yong","Chang Qing","Guang Tingbo","Zhuang Yan","Gustave Courbet",
"Pang Jun","John Constable","Fra Angelico","Caspar David Friedrich","Zhang Yibo","Zhang Chongren","Zhang Li","Zhang Zhanshan","Zhang Guolong","Zhang Xian",
"Zhang Wenxin","Zhang Xiaogang","Zhang Wo","Zhang Zuying","Zhang Yu","Zhang Zini","Zhang Fangcun","Zhang Chongqing","Zhang Qinruo","Zhang Tieyuan",
"Zhang Longji","Zhang Lei","Xu Weixin","Xu Tianli","Xu Yanzhou","Xu Beihong","Xu Yanting","Xu Qingfeng","Xu Qingwei","Edgar Degas",
"Eugène Delacroix","Xin Dongwang","Yun Shouping","Dai Shihe",None,"Dunhuang Mural Painters (Anonymous)","Wen Guozhang","Wen Zhengming","Viktor Smukrovich","Cao Dali",
"Zeng Chunfang","Zeng Fanzhi","Zhu Naizheng","Chu Teh-Chun","Zhu Chunlin","Zhu Weimin","Li Gonglin","Li Tang","Li Shijin","Li Zonghai",
"Li Cheng","Li Bin","Li Mingfeng","Li Ruinian","Li Zijian","Li Zigang","Li Guijun","Honoré Daumier","Du Jian","Yang Canjun",
"Yang Songlin","Yang Qiuren","Yang Hongtai","Yang Feiyun","Lin Gang","Lin Xiaochu","Lin Fengmian","Camille Corot","Juan Gris","Liang Kai",
"Vincent van Gogh","Chu Ge","Wu Mingzhong","Pablo Picasso","Camille Pissarro","Mao Benhua","Mao Yan","Yongle Palace Murals","Tang Xiaoming","Wang Yachen",
"Wang Zhijie","Shen Zhou","Shen Jiawei","Sha Qi","Sandro Botticelli","Hong Ling","Asai Chū","Tu Ke","Wen Bao","Pan Shixun",
"Pan Yuliang","Jiao Xiaojian","Xiong Ninghui","Wang Lijuan","Wang Hai","Wang Guang","Wang Keju","Wang Like","Wang Cunyu","Wang Hongjian",
"Wang Shaolun","Wang Yan","Wang Shikuo","Wang Zhenghua","Wang Dewei","Wang Huaiqing","Wang Yuezhi","Wang Wenbin","Wang Chun","Wang Yidong",
"Wang Yiguang","Wang Jiyuan","Wang Meng","Wang Xia","Shen Ling","Bai Renhai","Shi Tao","Qin Dahu","Cheng Conglin","Cheng Yajie",
"Cheng Li","Dou Hong","Jean-François Millet","Johannes Vermeer","Luo Zhongli","Luo Erchun","Luo Gongliu","Zhai Jianqun","Hu Yichuan","Hu Shanyu",
"Hu Tilin","Ai Zhongxin","Ai Shizhi","Ai Xuan","Su Tianci","Su Gaoli","Miao Huiyu","Fan Kuan","Hans Holbein","Claude Monet",
"Mo Pu","Ge Yudong","Ge Pengren","Dong Qichang","Dong Xiwen","Dong Yuan","Dong Wei","Edvard Munch","Cai Liang","Cai Xiaobin",
"Cai Haojie","Zang Erkang","Yuan Yuan","Yuan Zhengyang","Yuan Yunfu","Alfred Sisley","Paul Signac","Simone Martini","Zhan Jianjun","Jean-Marc Nattier",
"Xu Xingzhi","Chen Beixin","Gu Gang","Fei Zheng","He Wenqing","Zhao Yixiong","Zhao Lizhong","Zhao Youping","Zhao Dalu","Zhao Mengfu",
"Zao Wou-Ki","Lu Zhang","Leonardo da Vinci","Deng Jianjin","Shao Zenghu","Shao Jingkun","Shao Fei","Zou Qikui","Giuseppe Castiglione","Zheng Yumin",
"Zheng Xie","Zheng Yi","Guo Shaozong","Guo Runwen","Guo Xi","E Guijun","Jin Nong","Jin Sha","Zhong Han","Zhong Ling",
"Yan Ping","Yan Ping","Wen Shihong","Wen Lipeng","Yan Zhenduo","Yan Zhenfeng","Yan Wenxi","Alfred Wahlberg","Chen Yifeng","Chen Shining",
"Chen Danqing","Chen Junde","Chen Jian","Chen Yiming","Chen Jianxin","Chen Baoyi","Chen Zhenxin","Chen Hongshou","Chen Wanshan","Chen Yanning",
"Chen Yifei","Pierre-Auguste Renoir","Jin Zhilin","Jin Shangyi","Wei Qimei","Wei Ershen","Han Leran","Gu Liming","Yan Wenliang","Ma Changli",
"Ma Te","Ma Lu","Ma Yuan","Gao Youlin","Gao Xiaohua","Paul Gauguin","Gao Quan","Gao Chao","Kuncan","Peter Paul Rubens",
"Huang Gongwang","Huang Shen","Huang Youwei","Huang Shaoqiang","Long Liyou","Gong Qi",
]

def main(apply=False):
    need_cn = json.load(open('/tmp/need_cn.json'))  # [{aid,en}]
    need_en = json.load(open('/tmp/need_en.json'))  # [{aid,cn}]
    assert len(CN) == len(need_cn), f"CN len {len(CN)} != need_cn {len(need_cn)}"
    assert len(EN) == len(need_en), f"EN len {len(EN)} != need_en {len(need_en)}"
    cn_updates = [(need_cn[i]['aid'], CN[i]) for i in range(len(CN)) if CN[i]]
    en_updates = [(need_en[i]['aid'], EN[i]) for i in range(len(EN)) if EN[i]]
    cn_skip = [need_cn[i]['en'] for i in range(len(CN)) if not CN[i]]
    en_skip = [need_en[i]['cn'] for i in range(len(EN)) if not EN[i]]
    print(f"name_cn 待写 {len(cn_updates)} 条(跳过 {len(cn_skip)}: {cn_skip})")
    print(f"name_en 待写 {len(en_updates)} 条(跳过 {len(en_skip)}: {en_skip})")
    print("样例 cn:", cn_updates[:3], "...", cn_updates[-2:])
    print("样例 en:", en_updates[:3], "...", en_updates[-2:])
    if not apply:
        print("\n[dry-run] 加 --apply 才写库"); return

    d = json.load(open(os.path.expanduser("~/.aha_pg.json")))
    conn = psycopg2.connect(host=d.get('host','127.0.0.1'), port=d.get('port',5432),
                            dbname=d['dbname'], user=d['user'], password=d['password'])
    cur = conn.cursor(cursor_factory=RealDictCursor)
    all_aids = [a for a,_ in cn_updates] + [a for a,_ in en_updates]
    cur.execute("SELECT artist_id, name_cn, name_en FROM artists WHERE artist_id = ANY(%s)", (all_aids,))
    backup = {r['artist_id']: {'name_cn': r['name_cn'], 'name_en': r['name_en']} for r in cur.fetchall()}
    json.dump(backup, open('/tmp/name_backfill_backup.json','w'), ensure_ascii=False, indent=1)
    print(f"\n备份 {len(backup)} 行旧值 → /tmp/name_backfill_backup.json")
    try:
        n1=n2=0
        for aid, name in cn_updates:
            cur.execute("UPDATE artists SET name_cn=%s WHERE artist_id=%s AND (name_cn IS NULL OR name_cn='')", (name, aid)); n1+=cur.rowcount
        for aid, name in en_updates:
            cur.execute("UPDATE artists SET name_en=%s WHERE artist_id=%s AND (name_en IS NULL OR name_en='')", (name, aid)); n2+=cur.rowcount
        conn.commit()
        print(f"✅ 已提交:name_cn {n1} 行、name_en {n2} 行")
    except Exception as e:
        conn.rollback(); print("❌ 回滚:", e); raise
    finally:
        conn.close()

if __name__ == '__main__':
    main(apply='--apply' in sys.argv)
