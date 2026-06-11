#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规范风格标准(canonical style taxonomy)——中文为主,英文副,i18n 预留多语言。

问题:三来源 school 中英混杂、同风格多写法(impressionism/印象派/印象主义后印象主义…),
共 143 个原值。本模块:
  1) 定义 ~31 个规范风格(styles 表:style_id + name_zh + name_en + i18n jsonb + sort)。
  2) to_style_id(raw):有序关键词规则把任意原值(含未来新值)归一到 style_id。
  3) 入库适配器 import 它在写库时直接填 style_id;本脚本 __main__ 建表+回填存量。

用法: python3 style_norm.py            # 建 styles 表 + 给 works 回填 style_id
      python3 style_norm.py --check    # 只看映射覆盖,不写库
"""
import os, re, json, sys, argparse

# 规范风格表:大致按艺术史时序 sort。中文名=主显示,英文名=译版,i18n 后续补语种。
CANON = [
 ("medieval",               "中世纪艺术",     "Medieval Art",            10),
 ("renaissance",            "文艺复兴",       "Renaissance",             20),
 ("mannerism",              "风格主义",       "Mannerism",               25),
 ("baroque",                "巴洛克",         "Baroque",                 30),
 ("rococo",                 "洛可可",         "Rococo",                  40),
 ("classicism",             "古典主义",       "Classicism",              45),
 ("neoclassicism",          "新古典主义",     "Neoclassicism",           50),
 ("academicism",            "学院派",         "Academicism",             55),
 ("romanticism",            "浪漫主义",       "Romanticism",             60),
 ("realism",                "现实主义",       "Realism",                 70),
 ("pre_raphaelite",         "拉斐尔前派",     "Pre-Raphaelite Brotherhood", 75),
 ("impressionism",          "印象派",         "Impressionism",           80),
 ("neo_impressionism",      "新印象派",       "Neo-Impressionism",       85),
 ("post_impressionism",     "后印象派",       "Post-Impressionism",      90),
 ("symbolism",              "象征主义",       "Symbolism",               95),
 ("art_nouveau",            "新艺术运动",     "Art Nouveau",            100),
 ("fauvism",                "野兽派",         "Fauvism",                110),
 ("expressionism",          "表现主义",       "Expressionism",          115),
 ("cubism",                 "立体主义",       "Cubism",                 120),
 ("futurism",               "未来主义",       "Futurism",               125),
 ("dada",                   "达达主义",       "Dada",                   130),
 ("surrealism",             "超现实主义",     "Surrealism",             135),
 ("abstract_art",           "抽象艺术",       "Abstract Art",           140),
 ("abstract_expressionism", "抽象表现主义",   "Abstract Expressionism", 145),
 ("pop_art",                "波普艺术",       "Pop Art",                150),
 ("art_deco",               "装饰艺术",       "Art Deco",               155),
 ("ecole_de_paris",         "巴黎画派",       "École de Paris",         160),
 ("naive_art",              "素朴艺术",       "Naïve Art / Primitivism",165),
 ("ukiyo_e",                "浮世绘",         "Ukiyo-e",                170),
 ("orientalism",            "东方主义",       "Orientalism",            175),
 ("contemporary",           "现当代艺术",     "Contemporary Art",       180),
 ("other",                  "其它/未分类",    "Other",                  900),
]
CANON_IDS = {c[0] for c in CANON}

# 有序关键词规则:(正则, style_id)。先匹配更具体的(后印象 先于 印象;新古典 先于 古典)。raw 先转小写。
RULES = [
 (r"后印象|post[\s_-]?impress|纳比派|nabis",               "post_impressionism"),
 (r"新印象|neo[\s_-]?impress|点彩|分隔主义|division|pointillism", "neo_impressionism"),
 (r"印象|impress",                                        "impressionism"),
 (r"抽象表现|abstract[\s_-]?express|动作绘画|色域",       "abstract_expressionism"),
 (r"抽象|abstract|concretism|neoplasticism|constructivism|hard[\s_-]?edge|color[\s_-]?field|lyrical|tachisme|art\s*informel|synchromism|orphism|op\s*art|至上主义|构成主义|新造型主义|非形式艺术|硬边绘画|欧普艺术|极简主义|光效应艺术", "abstract_art"),
 (r"超现实|surreal|metaphysical|魔幻现实|幻想现实|automatic|自动绘画|自动主义|形而上", "surrealism"),
 (r"综合主义|synthetism",                                 "post_impressionism"),
 (r"立体|cubism|cubo|purism",                             "cubism"),
 (r"未来主义|futurism",                                   "futurism"),
 (r"野兽|fauv",                                           "fauvism"),
 (r"表现主义|expression|蓝骑士|桥社|新即物",              "expressionism"),
 (r"达达|dada",                                           "dada"),
 (r"波普|pop\s*art",                                      "pop_art"),
 (r"装饰艺术|art\s*deco",                                 "art_deco"),
 (r"新艺术|art\s*nouveau",                                "art_nouveau"),
 (r"象征|symbol",                                         "symbolism"),
 (r"浮世绘|ukiyo|yamato|日本主义|japonism",               "ukiyo_e"),
 (r"东方主义|orientalism",                                "orientalism"),
 (r"拉斐尔前|pre[\s_-]?raphaelite",                       "pre_raphaelite"),
 (r"巴黎画派|ecole[\s_-]?de[\s_-]?paris|école",           "ecole_de_paris"),
 (r"原始主义|primitiv|naive|naïve|素朴|素人|art\s*brut|outsider|kitsch", "naive_art"),
 (r"学院|academ",                                         "academicism"),
 (r"新古典|neo[\s_-]?classic",                            "neoclassicism"),
 (r"古典主义|classicism|古希腊|古罗马",                   "classicism"),
 (r"洛可可|rococo",                                       "rococo"),
 (r"巴洛克|baroque|tenebrism|荷兰黄金",                    "baroque"),
 (r"样式主义|矫饰|风格主义|mannerism",                    "mannerism"),
 (r"文艺复兴|renaissance|国际哥特|international\s*gothic|1[56]世纪|佛罗伦萨|威尼斯画派|锡耶纳", "renaissance"),
 (r"哥特|gothic|拜占庭|byzantine|中世纪|medieval|13-14世纪|罗马式", "medieval"),
 (r"浪漫主义|romantic|biedermeier",                       "romanticism"),
 (r"现实主义|realism|naturalism|自然主义|地方主义|社会现实|社会主义现实|verism|luminism|tonalism|色调主义|intimism|当代现实|美国现实|照相写实|超写实|巴比松", "realism"),
 (r"当代|现代|contemporary|20世纪|战后|后现代|两次世界大战|modernism|近现代|neo[\s_-]?figurative|feminist|muralism|新现实|nouveau|观念艺术|算法与生成|街头|涂鸦|数字绘画|沉浸与环境|后互联网|区块链|nft|贫穷艺术|大地艺术", "contemporary"),
]
_COMPILED = [(re.compile(p, re.I), sid) for p, sid in RULES]

def to_style_id(raw):
    """任意 school 原值 → 规范 style_id;空/无匹配 → None(交由 'other' 或留空)。"""
    if not raw or not str(raw).strip():
        return None
    s = str(raw).split(";")[0].strip().lower()    # 多标签取第一个
    for rx, sid in _COMPILED:
        if rx.search(s):
            return sid
    return "other"

# ---------------- 建表 + 回填 ----------------
def _pg():
    import psycopg2
    d = json.load(open(os.path.expanduser("~/.aha_pg.json")))
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    cn = _pg(); cur = cn.cursor()
    cur.execute("SELECT school, count(*) FROM works WHERE school IS NOT NULL AND school<>'' GROUP BY school")
    rows = cur.fetchall()
    # 覆盖统计
    from collections import Counter
    bucket = Counter(); other_samples = []
    mapping = {}
    for school, n in rows:
        sid = to_style_id(school)
        mapping[school] = sid
        bucket[sid] += n
        if sid == "other": other_samples.append((school, n))
    total = sum(n for _, n in rows)
    print(f"原值 {len(rows)} 个 → 规范 {len([k for k in bucket if k!='other'])} 类,覆盖 {total} 作品")
    for sid, n in bucket.most_common():
        zh = next((c[1] for c in CANON if c[0] == sid), sid)
        print(f"  {sid:<24} {zh:<10} {n}")
    if other_samples:
        print("  ↳ other 明细:", sorted(other_samples, key=lambda x: -x[1])[:20])
    if a.check:
        return

    # 建 styles 表
    cur.execute("""CREATE TABLE IF NOT EXISTS styles(
        style_id text PRIMARY KEY, name_zh text NOT NULL, name_en text,
        i18n jsonb NOT NULL DEFAULT '{}', sort int)""")
    for sid, zh, en, sort in CANON:
        cur.execute("""INSERT INTO styles(style_id,name_zh,name_en,sort) VALUES(%s,%s,%s,%s)
                       ON CONFLICT (style_id) DO UPDATE SET name_zh=EXCLUDED.name_zh,
                       name_en=EXCLUDED.name_en, sort=EXCLUDED.sort""", (sid, zh, en, sort))
    cur.execute("ALTER TABLE works ADD COLUMN IF NOT EXISTS style_id text")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_works_style ON works(style_id)")
    # 按 distinct school 批量回填(143 条 UPDATE,快)
    upd = 0
    for school, sid in mapping.items():
        cur.execute("UPDATE works SET style_id=%s WHERE school=%s", (sid, school))
        upd += cur.rowcount
    cn.commit()
    print(f"✓ styles 表 {len(CANON)} 类;works.style_id 回填 {upd} 件")
    cur.execute("SELECT count(*) FROM works WHERE style_id IS NULL")
    print(f"  仍空 style_id(无school): {cur.fetchone()[0]}")
    cn.close()

if __name__ == "__main__":
    main()
