#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从油画数据库(al_artist/al_work)抽两层结构化信息:
  ② 影响谱系边: affect_by(受影响)/affect_to(影响了)/disciple(传人) → 有向边(影响/师承)
  ① 题材层标签: al_work.subject_names 频率法抽题材词表 + per-work tags

输出:
  web/data/kg_yh_lineage.json   影响/师承边(尽量映射到 ARTIST.<slug>)
  web/data/kg_yh_subjects.json  题材词表(频率排序)
  Postgres work_subjects 表      已灌作品的 per-work 题材(--apply)

用法: python3 extract_yh_meta.py [--apply]   (默认 dry-run,只导JSON+打印;--apply 额外写 work_subjects 表)
"""
import os, sys, re, json, argparse
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from ingest_yh import iter_rows, pg_conn

SD = "/tmp/youhua_db/油画数据库"
WEB = "/home/ubuntu/users/qiuyiwu/aha-art/web/data"
SEP = re.compile(r"[，,、；;／/\s]+")

# 媒介/材质/体裁/时期等"非题材"停用词(题材层要剔)
STOP = set("""油画 油彩 画布 布面 纸本 绢本 水彩 水粉 素描 版画 雕塑 壁画 蛋彩 丙烯 板上油画 木板
中国画 国画 当代艺术 现代艺术 20世纪艺术 抽象艺术 装置 摄影 综合材料 纸上 布上 麻布 木板油画
印象派 印象主义 后印象主义 野兽派 立体派 立体主义 表现主义 超现实主义 抽象表现主义 浪漫主义
现实主义 古典主义 新古典主义 巴洛克 洛可可 象征主义 文艺复兴 风格主义 未来主义 至上主义""".split())

def norm(s): return (s or "").strip()

def load_artist_names():
    """al_artist: id→中文名; 名/西文名/别名 → al_id 反查索引。"""
    id2cn = {}; name2id = {}
    for r in iter_rows(os.path.join(SD, "al_artist.sql"), "al_artist"):
        if len(r) < 4: continue
        aid, cn, en, by = r[0], norm(r[1]), norm(r[2]), norm(r[3])
        if cn: id2cn[aid] = cn
        names = [cn, en] + [x.strip() for x in re.split(r"[,，;；]", by) if x.strip()]
        # 补"·"后段短名(萨尔瓦多·达利→达利)与"·"前段,堵艺术家简称漏进题材
        for base in [cn] + [x.strip() for x in re.split(r"[,，;；]", by) if x.strip()]:
            if "·" in base:
                parts = [p for p in base.split("·") if len(p) >= 2]
                names += parts
        for nm in names:
            if nm and nm not in name2id: name2id[nm] = aid
    return id2cn, name2id

def load_kg_slugs():
    """kg_artists.json: 中文名/英文名 → ARTIST.<slug>(curated 282)。"""
    d = json.load(open(os.path.join(WEB, "kg_artists.json"), encoding="utf-8"))
    cn2slug = {}
    for slug, a in d.get("artists", {}).items():
        for nm in [norm(a.get("cn")), norm(a.get("en"))]:
            if nm: cn2slug[nm] = slug
    return cn2slug

# ---------------- ② 谱系边 ----------------
def extract_lineage(id2cn, name2id, cn2slug):
    rows = list(iter_rows(os.path.join(SD, "al_artist.sql"), "al_artist"))
    edges = {}   # (src_cn,dst_cn,rel) -> dict
    raw = matched = 0
    def resolve(frag):
        frag = frag.strip(" 。.·")
        if not frag or len(frag) > 9: return None       # 过长 = 散文,丢
        if frag in STOP: return None                    # 流派/媒介词
        if frag in name2id: return frag                 # 命中 al_artist 名
        if frag in cn2slug: return frag
        return None
    for r in rows:
        if len(r) < 18: continue
        me = norm(r[1])
        if not me: continue
        for col, rel, direction in [(10,"影响","in"), (11,"影响","out"), (17,"师承","out")]:
            val = norm(r[col]) if col < len(r) else ""
            if not val: continue
            # 整段超长且无分隔 → 散文,跳过
            frags = [f for f in SEP.split(val) if f]
            for f in frags:
                raw += 1
                other = resolve(f)
                if not other or other == me: continue
                matched += 1
                src, dst = (other, me) if direction == "in" else (me, other)
                key = (src, dst, rel)
                if key not in edges:
                    edges[key] = {"src_cn": src, "dst_cn": dst, "rel": rel,
                                  "src": cn2slug.get(src), "dst": cn2slug.get(dst)}
    elist = list(edges.values())
    both_curated = sum(1 for e in elist if e["src"] and e["dst"])
    out = {"meta": {"source": "油画数据库 al_artist.affect_by/affect_to/disciple",
                    "note": "人工考据的影响/师承关系;src/dst 为 ARTIST.slug(命中curated 282)否则 null,另存中文名",
                    "n_edges": len(elist), "n_both_curated": both_curated,
                    "raw_fragments": raw, "matched": matched},
           "edges": elist}
    json.dump(out, open(os.path.join(WEB, "kg_yh_lineage.json"), "w"),
              ensure_ascii=False, indent=1)
    print(f"② 谱系边: 原始片段 {raw} → 命中人名 {matched} → 去重边 {len(elist)} "
          f"(两端都在curated 282 的 {both_curated} 条可并入 kg_artist_lineage)")
    rels = Counter(e["rel"] for e in elist)
    print(f"   关系: {dict(rels)}")
    print("   样例(两端 curated):")
    for e in [x for x in elist if x["src"] and x["dst"]][:6]:
        print(f"     {e['src_cn']}({e['src']}) -{e['rel']}-> {e['dst_cn']}({e['dst']})")
    return elist

# ---------------- ① 题材层 ----------------
def extract_subjects(name2id, apply):
    rows = list(iter_rows(os.path.join(SD, "al_work.sql"), "al_work"))
    cnt = Counter()
    work_tokens = {}  # al_work_id -> [tokens]
    for r in rows:
        if len(r) < 46: continue
        wid = r[0]; sn = norm(r[45])
        if not sn: continue
        toks = [t.strip() for t in SEP.split(sn) if t.strip()]
        # 过滤:媒介停用词、命中艺术家名(作者/无关人名)、纯英文、过长(标题)
        keep = []
        for t in toks:
            if t in STOP or t in name2id: continue
            if len(t) > 6 or len(t) < 2: continue        # 题材词一般 2–6 字
            if re.fullmatch(r"[A-Za-z0-9 ]+", t): continue
            if t.endswith("艺术家") or t in ("绘画","其他画","写实","油画作品","作品"): continue
            keep.append(t)
        if keep:
            work_tokens[wid] = keep
            cnt.update(set(keep))
    # 词表 = 频率 ≥ 30
    vocab = [(w, c) for w, c in cnt.most_common() if c >= 30]
    vset = set(w for w, _ in vocab)
    out = {"meta": {"source": "油画数据库 al_work.subject_names",
                    "note": "频率法抽题材词(≥30次),已剔媒介/作者名/标题;per-work tags 见 Postgres work_subjects",
                    "n_vocab": len(vocab), "n_works_with_subjects": len(work_tokens)},
           "vocab": [{"subject": w, "count": c} for w, c in vocab]}
    json.dump(out, open(os.path.join(WEB, "kg_yh_subjects.json"), "w"),
              ensure_ascii=False, indent=1)
    print(f"\n① 题材层: {len(work_tokens):,} 件有题材 → 词表 {len(vocab)} 个(频率≥30)")
    print("   高频题材:", "、".join(f"{w}({c})" for w, c in vocab[:25]))

    if not apply:
        print("\n[dry-run] 已导出两个 JSON。--apply 额外把 per-work 题材写入 work_subjects 表。")
        return
    # 写 work_subjects(只写已灌入库的 yh 作品)
    cn = pg_conn(); cur = cn.cursor()
    cur.execute("""create table if not exists work_subjects(
                     work_id bigint, subject text, source text default 'yh',
                     primary key(work_id, subject))""")
    cur.execute("create index if not exists ix_work_subjects_subj on work_subjects(subject)")
    cur.execute("select work_id, src_work_id from works where source_batch like 'yh%' and src_work_id is not null")
    src2wid = {s: w for w, s in cur.fetchall()}
    n = 0; rows_ins = []
    for awid, toks in work_tokens.items():
        wid = src2wid.get(awid)
        if not wid: continue
        for t in toks:
            if t in vset: rows_ins.append((wid, t))
    from psycopg2.extras import execute_values
    cur.execute("delete from work_subjects where source='yh'")
    execute_values(cur, "insert into work_subjects(work_id,subject) values %s on conflict do nothing", rows_ins)
    cn.commit()
    cur.execute("select count(*), count(distinct work_id) from work_subjects")
    a, b = cur.fetchone()
    print(f"   写入 work_subjects: {a:,} 条标签覆盖 {b:,} 件已灌作品")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    id2cn, name2id = load_artist_names()
    cn2slug = load_kg_slugs()
    print(f"al_artist 名字索引 {len(name2id):,} | curated ARTIST.slug {len(cn2slug)}")
    extract_lineage(id2cn, name2id, cn2slug)
    extract_subjects(name2id, a.apply)

if __name__ == "__main__":
    main()
