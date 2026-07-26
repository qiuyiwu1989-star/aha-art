#!/usr/bin/env python3
"""造物云 AI 生成图库分类脚本。
基于 workflow_name + input_prompt 关键词规则匹配，写入 gen_file.category。

用法:
  python3 classify_gen.py [--dry-run]
"""
import json, re, os, argparse
import psycopg2

# ── 分类规则 ──
# 优先级从高到低：先匹配的 wins

# 1. workflow_name 直接映射（非主 workflow 的小工具类）
WORKFLOW_MAP = {
    "wan21姿势控制视频": "tool/video",
    "图片去水印": "tool/watermark",
    "图片放大4倍": "tool/upscale",
    "Instant照片换脸": "tool/face_swap",
    "智能抠图": "tool/cutout",
    "CAKA-图生文": "tool/vlm",
    "CAKA文生文": "tool/text",
    "文本生成成衣": "fashion/render",
    "成衣局部改款（有参考图）": "fashion/redesign",
    "成衣指定模特上身": "fashion/redesign",
    "成衣提取花型": "fashion/fabric",
    "花型生成花型（多图）": "pattern/gen",
    "花型智能扩图": "pattern/gen",
    "潘多拉手链挂件批量生成": "cultural/jewelry",
    "CMF产品融合": "product/cmf",
    "万物皆可钻": "cultural/jewelry",
    "图片生成图片": "product/render",
    "图片去水印": "tool/watermark",
}

# 2. prompt 关键词 → 类别（按优先级排序，先匹配的 wins）
PROMPT_RULES = [
    # ── 产品设计（最高优先级，因为占比最大）──
    (r"产品.*(?:场景|场景图|场景合成|场景视觉)|商品级.*场景|产品图.*场景", "product/scene"),
    (r"(?:CMF|材质迁移|材质转译|颜色.*材料.*表面处理)", "product/cmf"),
    (r"(?:六视图|三视图|右视图|左视图|正视图|俯视图|专利.*视图|正交投影)", "product/patent"),
    (r"(?:产品|物品).*(?:抠出|抠图|白底|白色背景|透明背景)|(?:抠出|提取).*(?:产品|物品)", "tool/cutout"),
    (r"(?:设计|生成|全新).*(?:挂钩|纸巾盒|键帽|收纳柜|淋浴|沙发|椅子|桌子|灯具|杯子|瓶|盒|柜|架|床|灯|出水口|键盘)", "product/render"),
    (r"(?:产品|工业设计).*(?:渲染|效果图|32K|超高清)|纯色.*背景.*摄影.*光影", "product/render"),
    (r"(?:3d|3D).*(?:渲染|效果图)|(?:渲染|效果图).*(?:产品|工业)", "product/render"),
    (r"(?:材质球|材质.*白底|白底.*材质)", "product/render"),
    (r"(?:抽屉|收纳|挂钩|纸巾盒|键帽|淋浴|沙发|椅子|桌子|灯具|杯子|瓶|盒|柜|架|键盘).*(?:设计|全新|造型)", "product/render"),
    (r"(?:泛化|变体|方案).*(?:产品|正视图|组件)", "product/render"),

    # ── IP/角色设计（细分）──
    # IP 贴图/联名（最高优先级）
    (r"(?:IP|ip).*(?:贴图|联名|应用|丝印|移印|热转印|UV打印)", "ip/decal"),
    (r"(?:贴图|联名|decal).*(?:IP|ip|产品|家居|日用)", "ip/decal"),
    # 手办/潮玩
    (r"(?:手办|figure|pvc|模型|盲盒|潮玩|玩具|公仔).*(?:角色|形象|设计|展示)", "ip/figure"),
    (r"(?:IP|ip|角色).*(?:手办|figure|pvc|模型|盲盒|潮玩|玩具|公仔)", "ip/figure"),
    # 3D 角色
    (r"(?:3d|3D|三维|立体|渲染|c4d|octane|blender).*(?:角色|形象|ip|IP|人物)", "ip/3d"),
    (r"(?:IP|ip|角色).*(?:3d|3D|三维|立体|渲染|c4d|octane)", "ip/3d"),
    # Q版/可爱
    (r"(?:Q版|q版|卡通|可爱|萌|kawaii|chibi|圆滚滚|呆萌).*(?:角色|形象|造型|icon|图)", "ip/cute"),
    (r"(?:角色|形象).*(?:Q版|卡通|可爱|萌)", "ip/cute"),
    (r"(?:icon).*(?:风格|生成|设计)|生成.*icon", "ip/cute"),
    (r"(?:cartoon|cute|kawaii|chibi).*(?:design|style|icon|character)", "ip/cute"),
    (r"(?:轮廓|剪影).*(?:生成|ip|IP|角色|icon)", "ip/cute"),
    # 动漫/漫画
    (r"(?:动漫|漫画|二次元|anime|manga|日系).*(?:角色|人物|风格)", "ip/anime"),
    # 虚拟人/数字人
    (r"(?:虚拟|数字人|y3k|Y3K|ai.*角色|虚拟偶像|vtuber|VTuber)", "ip/virtual"),
    # 传统文化角色
    (r"(?:皮影|剪纸|非遗|传统.*角色|山海经|京剧|脸谱)", "ip/cultural"),
    # 动物/宠物
    (r"(?:宠物|猫|狗|兔|熊|动物|萌宠|鸭|鹅|猪|鼠).*(?:角色|形象|卡通|ip|IP)", "ip/pet"),
    # 食物/美食
    (r"(?:食物|美食|餐饮|甜点|水果|食品).*(?:角色|形象|ip|IP|卡通)", "ip/food"),
    # 吉祥物
    (r"(?:吉祥物|mascot|品牌.*ip|ip.*品牌)", "ip/mascot"),
    # 角色设计/融合
    (r"(?:角色卡|角色设计|character|人物设定|角色融合|角色替换)", "ip/character"),
    (r"(?:IP|ip).*(?:形象|角色|设计|生成|融合|卡片)|(?:生成|设计).*IP", "ip/character"),
    (r"(?:角色|人物).*(?:融合|替换|插画)", "ip/fusion"),
    # 动物（兜底）
    (r"(?:加菲猫|猫|狗|兔|熊|鸭|鹅|猪|鼠)", "ip/pet"),

    # ── 服装设计 ──
    (r"(?:线稿|技术线稿|技术图|铅笔手绘稿).*(?:服装|衣服|成衣)", "fashion/lineart"),
    (r"(?:服装|衣服|成衣).*(?:线稿|技术图|蓝图)", "fashion/lineart"),
    (r"(?:羽绒服|冲锋衣|卫衣|T恤|连衣裙|外套|夹克|西装|衬衫|裤子|裙|hooded|sweatshirt|poncho).*(?:效果图|渲染|3D|展示|真实)", "fashion/render"),
    (r"(?:改款|改版|改色).*(?:服装|衣服|成衣)|(?:服装|衣服|成衣).*(?:改款|改版)", "fashion/redesign"),
    (r"(?:面料|织物|布料).*(?:纹理|图案|花型|应用)", "fashion/fabric"),
    (r"冲锋衣|羽绒服|卫衣|连衣裙|外套|夹克", "fashion/render"),
    (r"(?:hooded|sweatshirt|poncho|fabric|clothing|garment)", "fashion/render"),

    # ── 油画/艺术（细分主题）──
    # 人体艺术（最高优先级）
    (r"(?:人体艺术|裸体|裸女|美人).*(?:绘画|风格|唯美|构图)", "art/figure"),
    (r"(?:油画|绘画|艺术).*(?:人体|裸体|美人|罗马式)", "art/figure"),
    # 幻兽/山海经
    (r"(?:油画|绘画).*(?:幻兽|山海经|奇兽|神话)", "art/fantasy"),
    (r"(?:幻兽|山海经|奇兽|龙|凤|麒麟)", "art/fantasy"),
    # 江南古镇/水乡
    (r"(?:油画|绘画).*(?:古镇|水乡|江南|周庄|西塘|乌镇|南浔|甪直|同里|枕水)", "art/jiangnan"),
    (r"(?:古镇|江南|水乡|乌镇|南浔|同里|周庄|西塘|甪直).*(?:油画|绘画|风景)", "art/jiangnan"),
    # 杭州西湖
    (r"(?:油画|绘画).*(?:西湖|雷峰|断桥|曲院风荷|苏堤|白堤|杭州)", "art/westlake"),
    (r"(?:西湖|雷峰|断桥|曲院风荷|杭州).*(?:油画|绘画)", "art/westlake"),
    # 渔村/海港
    (r"(?:油画|绘画).*(?:渔村|渔港|渔船|渔民|码头|海边|海港|海岸|渔火)", "art/fishing"),
    (r"(?:渔村|渔港|渔船|渔民|码头|海边|海港).*(?:油画|绘画)", "art/fishing"),
    # 花卉/静物
    (r"(?:油画|绘画).*(?:花卉|静物|花瓶|花朵|花束|水果)", "art/flower"),
    (r"(?:花卉|静物|花瓶|花朵|花束).*(?:油画|绘画)", "art/flower"),
    # 骏马
    (r"(?:油画|绘画).*(?:八骏|骏马|奔马|马匹)", "art/horse"),
    (r"(?:八骏|骏马|奔马|马).*(?:油画|绘画)", "art/horse"),
    # 星空/夜景
    (r"(?:油画|绘画).*(?:星空|夜景|月光|夜空|星辰)", "art/nightscape"),
    # 人物/肖像
    (r"(?:油画|绘画).*(?:人物|肖像|教师|老者|妇人|少女|舞者|渔民|林徽因)", "art/portrait"),
    # 建筑/古建
    (r"(?:油画|绘画).*(?:建筑|楼阁|亭|桥|城墙|宫殿|古建)", "art/architecture"),
    # 山水/自然
    (r"(?:油画|绘画).*(?:山|水|云|雾|瀑布|溪|谷|峰|海|湖|江|河)", "art/landscape"),
    # 西方流派
    (r"(?:油画|绘画).*(?:印象派|野兽派|立体主义|表现主义|抽象|后印象派|新印象派)", "art/western"),
    (r"(?:油画|写实主义|古典写实|伦勃朗|维米尔|新写实)", "art/western"),
    # 通用油画兜底
    (r"^油画[，,]|^油画\s", "art/landscape"),

    # ── 文创设计 ──
    (r"(?:螺钿|螺甸).*(?:产品|设计|首饰|器物|文创|纹样|几何)", "cultural/nacre"),
    (r"(?:非遗|传统工艺).*(?:灯|具|文创|设计|蓝染|夹缬)", "cultural/heritage"),
    (r"(?:火漆|印章).*(?:设计|生成|融合)", "cultural/stamp"),
    (r"(?:红包|礼盒).*(?:设计|插画|生成)", "cultural/stationery"),
    (r"(?:博物馆|文物|青铜|犀尊|西汉|复刻|上色)", "cultural/heritage"),
    (r"(?:非遗|蓝染|夹缬|靛蓝|传统工艺)", "cultural/heritage"),

    # ── 花型/图案 ──
    (r"(?:花型|图案).*(?:生成|设计|数字化|印刷|提取)", "pattern/gen"),
    (r"(?:四方连续|连续图案|无缝图案)", "pattern/gen"),
    (r"(?:几何纹样|纹样).*(?:绘制|设计|螺钿)", "pattern/geometric"),
    (r"(?:图案|纹样).*(?:数字化|提取|印刷)", "pattern/digit"),

    # ── 场景/空间 ──
    (r"(?:直播间|直播).*(?:视觉|场景|空间|描述)", "scene/livestream"),
    (r"(?:空间|室内|房间).*(?:设计|渲染|视觉)", "scene/space"),

    # ── 图像工具 ──
    (r"(?:抠图|抠出|提取.*主体|去除背景|白色背景|透明背景)", "tool/cutout"),
    (r"(?:去水印|去除水印|水印去除)", "tool/watermark"),
    (r"(?:放大|超分|upscale|4倍|超高清)", "tool/upscale"),
    (r"(?:换脸|face.?swap)", "tool/face_swap"),
    (r"(?:线稿|草稿|素描).*(?:提取|转换|生成)", "tool/lineart"),
    (r"(?:剖面|截面|示意图).*(?:图|生成)", "tool/diagram"),
    (r"(?:皱纹|去除|去掉|变红|空白区域|不变).*(?:衣服|服装|fabric|wrinkle)", "tool/edit"),
    (r"(?:保持一致|保持原图|完全不变)", "tool/edit"),

    # ── 补充：英文关键词 ──
    (r"(?:product|industrial).*(?:design|render|rendering|photography)", "product/render"),
    (r"(?:oil\s*painting|classical\s*realism|renaissance)", "art/oil_painting"),
    (r"(?:pattern|textile|fabric).*(?:design|print|generation)", "pattern/gen"),
]

# 3. 各主 workflow 的默认分类（当 prompt 规则全部不匹配时）
WORKFLOW_DEFAULTS = {
    "CAKA-文生图-图生图": "product/render",   # 40% 是产品设计
    "CAKA多图融合": "product/render",          # 大部分是工业设计任务
    "飞书-多图生单图": "product/render",        # 绝大部分是产品配色迁移
    "单文生单图": "product/render",
    "单图生单图": "product/render",
    "单图单文生成单文": "product/render",
    "单文生多图": "product/render",
    "单图+多图生多图": "product/render",
    "多图生多图（多批次）": "product/render",
}


def classify_prompt(prompt, workflow_name):
    """根据 prompt 和 workflow_name 返回分类标签"""
    if not prompt:
        prompt = ""

    # 1. workflow 直接映射（小工具类）
    if workflow_name in WORKFLOW_MAP:
        return WORKFLOW_MAP[workflow_name]

    # 2. prompt 关键词匹配
    for pattern, category in PROMPT_RULES:
        if re.search(pattern, prompt, re.IGNORECASE):
            return category

    # 3. 各 workflow 的默认分类
    if workflow_name in WORKFLOW_DEFAULTS:
        return WORKFLOW_DEFAULTS[workflow_name]

    # 4. 最终兜底
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印统计，不写库")
    a = ap.parse_args()

    with open(os.path.expanduser("~/.aha_pg.json")) as f:
        cfg = json.load(f)
    cn = psycopg2.connect(host=cfg["host"], port=cfg["port"], dbname=cfg["dbname"],
                          user=cfg["user"], password=cfg["password"])
    cn.autocommit = False
    cur = cn.cursor()

    # 拉取所有 gen_run
    cur.execute("""SELECT r.instance_id, r.workflow_name, r.input_prompt
                   FROM gen_run r
                   WHERE r.source = 'zaowuyun_team' AND r.status = 'COMPLETED'""")
    rows = cur.fetchall()
    print(f"共 {len(rows)} 条 COMPLETED 记录")

    # 分类
    stats = {}
    updates = []
    for instance_id, wf_name, prompt in rows:
        cat = classify_prompt(prompt, wf_name)
        stats[cat] = stats.get(cat, 0) + 1
        updates.append((cat, instance_id))

    # 打印子类统计
    print("\n子类统计：")
    print("-" * 55)
    for cat, cnt in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {cat:35s} {cnt:>6d}")

    # 打印大类汇总
    print("\n大类汇总：")
    print("-" * 55)
    major_stats = {}
    for cat, cnt in stats.items():
        major = cat.split("/")[0]
        major_stats[major] = major_stats.get(major, 0) + cnt
    for major, cnt in sorted(major_stats.items(), key=lambda x: -x[1]):
        pct = cnt * 100.0 / len(rows)
        bar = "█" * int(pct / 2)
        print(f"  {major:15s} {cnt:>6d}  ({pct:5.1f}%)  {bar}")

    if a.dry_run:
        print("\n[dry-run] 不写库")
        cn.close()
        return

    # 写入 gen_file.category
    print("\n写入 gen_file.category ...")
    updated = 0
    for cat, instance_id in updates:
        cur.execute("""UPDATE gen_file SET category = %s
                       WHERE instance_id = %s AND source = 'zaowuyun_team'""",
                    (cat, instance_id))
        updated += cur.rowcount

    cn.commit()
    print(f"已更新 {updated} 条 gen_file 记录")

    # 验证
    cur.execute("""SELECT category, COUNT(*) FROM gen_file
                   WHERE source = 'zaowuyun_team' AND category IS NOT NULL
                   GROUP BY category ORDER BY COUNT(*) DESC""")
    print("\n验证 gen_file.category 分布：")
    for cat, cnt in cur.fetchall():
        print(f"  {cat:35s} {cnt:>6d}")

    cn.close()
    print("\n完成!")


if __name__ == "__main__":
    main()
