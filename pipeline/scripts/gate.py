#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""入库整理闸门(intake gate):把"大量素材"沉淀成"带标注的核心资产"。

两层模型:
  素材层  = 所有已灌库的 works(status=pending),COS 原图+行永久保留,绝不物理删。
  核心资产 = 过闸晋升的优质子集(status=kept) + VLM 6维标注;画廊只读它。
  被刷下来的标 status=rejected(低质/非画作)或 dup(近重复),留底可回溯/可反悔。

三阶段(越往后越贵):
  dedup  — phash 近重复聚类,每簇留最高分辨率主图,其余标 dup(无需 VLM)。
  vlm    — 对幸存 pending 并发调 mimo-v2.5,一次给「判定 keep/reject + 质量分 + 6维标注」。
  stats  — 看各状态分布 + 最近被剔清单。

通用、可复用:任何新批次素材灌库后跑同一道闸门即可。
  python3 gate.py dedup  [--batch B] [--threshold 6]
  python3 gate.py vlm    [--batch B] [--limit N] [--workers 6] [--max-px 768]
  python3 gate.py stats  [--batch B] [--reject-list 40]
"""
import os, sys, io, json, time, argparse, base64, urllib.request, threading, re
from concurrent.futures import ThreadPoolExecutor, as_completed

from qcloud_cos import CosConfig, CosS3Client
from PIL import Image, ImageFilter
import psycopg2
from psycopg2.extras import Json

Image.MAX_IMAGE_PIXELS = None
SRC_BUCKET = "aha-1254041526"

# ---------- 凭据 ----------
def _cfg(p): return json.load(open(os.path.expanduser(p)))
def cos_client():
    d = _cfg("~/.aha_cos.json")
    return CosS3Client(CosConfig(Region=d["region"], SecretId=d["secret_id"], SecretKey=d["secret_key"],
                                 Timeout=30))
def pg_conn():
    d = _cfg("~/.aha_pg.json")
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"],
                            user=d["user"], password=d["password"])
def mimo_cfg():
    m = _cfg("~/.aha_mimo.json")
    base = m["endpoint"].rstrip("/")
    if not base.endswith("/messages"): base += "/v1/messages"
    return base, m["key"], m["model"]

CL = cos_client()
_tls = threading.local()
def cos():  # COS 客户端非线程安全,每线程一份
    if not hasattr(_tls, "cl"): _tls.cl = cos_client()
    return _tls.cl

# ====================================================================
# 阶段一:phash 近重复聚类(无 VLM)
# ====================================================================
def _ph_int(h):
    try: return int(h, 16)
    except Exception: return None

def dedup(batch=None, threshold=6):
    conn = pg_conn(); cur = conn.cursor()
    where = "WHERE f.phash IS NOT NULL AND w.status='pending'"
    args = []
    if batch: where += " AND w.source_batch=%s"; args.append(batch)
    cur.execute(f"""SELECT w.work_id, f.file_id, f.phash, f.width*f.height
                    FROM works w JOIN files f ON f.work_id=w.work_id {where}""", args)
    rows = cur.fetchall()
    items = [(wid, fid, _ph_int(ph), px or 0) for wid, fid, ph, px in rows if _ph_int(ph) is not None]
    n = len(items)
    print(f"[dedup] {n} 张参与近重复聚类 (hamming≤{threshold})")

    # 并查集 + O(n²) 海明(2000 量级够用;>20000 自动退化为精确 phash 分组)
    parent = list(range(n))
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[rb] = ra

    if n <= 20000:
        for i in range(n):
            pi = items[i][2]
            for j in range(i+1, n):
                if (pi ^ items[j][2]).bit_count() <= threshold:
                    union(i, j)
            if i % 500 == 0 and i: print(f"  聚类 {i}/{n}")
    else:  # 大批量:只按精确 phash 分组
        seen = {}
        for idx, it in enumerate(items):
            seen.setdefault(it[2], []).append(idx)
        for grp in seen.values():
            for k in grp[1:]: union(grp[0], k)

    clusters = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    n_dup = n_cluster = 0
    for root, members in clusters.items():
        if len(members) < 2: continue
        n_cluster += 1
        members.sort(key=lambda i: -items[i][3])      # 像素最多者当主图
        keep_i = members[0]; keep_wid = items[keep_i][0]
        loser_wids = [items[i][0] for i in members[1:]]
        member_fids = [items[i][1] for i in members]
        cur.execute("INSERT INTO dup_clusters(work_id, member_file_ids, reason) VALUES(%s,%s,%s)",
                    (keep_wid, member_fids, f"phash≤{threshold}"))
        cur.executemany("UPDATE works SET status='dup', reject_reason='near_dup' WHERE work_id=%s AND status='pending'",
                        [(w,) for w in loser_wids])
        n_dup += len(loser_wids)
    conn.commit()
    print(f"[dedup] {n_cluster} 个近重复簇,标 dup {n_dup} 张,主图保留 {n_cluster} 张")
    conn.close()

# ====================================================================
# 阶段二:VLM 判定 + 标注(并发)
# ====================================================================
ANCHORS = "喜悦 鲜活 热烈 崇高 张力 恐惧 神秘 忧伤 孤独 怀旧 虚无 沉思 平静 空灵"
# 策展分类 → 入库状态(三路分流):
#   绘画类(2D 画面艺术)= 核心资产 kept;非绘画实物(3D/翻拍)= 单独归档 archived;真垃圾 = rejected
CAT_KEPT     = {"painting", "drawing", "watercolor", "print", "fresco", "pastel", "gouache", "tempera", "ink"}
CAT_ARCHIVE  = {"sculpture", "artifact", "architecture", "installation", "ceramic", "textile", "other_artwork"}
CAT_REJECT   = {"detail_crop", "sketch", "low_quality", "non_art", "empty"}
def cat_to_status(cat):
    if cat in CAT_KEPT: return "kept"
    if cat in CAT_ARCHIVE: return "archived"
    if cat in CAT_REJECT: return "rejected"
    return "rejected"   # 未知保守归 rejected,留底可回溯

# 与线上标注库 kg_artwork_v2.json(kg-artworks.html 渲染)同一套 V2 六维 schema + 策展头
GATE_PROMPT = (
"预设你是艺术界大师 + 策展闸门 + 情绪分析师 + 名画鉴定师。看这张图,先判定它属于哪类、是否够格,尽力识别作者与作品名,再做完整系统描述。只输出一个 JSON(不要解释/不要代码块):\n"
"{\n"
'"category":"严格从这些英文键选1: painting(架上绘画/油画/丹培拉) drawing(素描) watercolor(水彩) print(版画) fresco(壁画) sculpture(雕塑照片) artifact(器物/工艺品实物照) architecture(建筑照) installation(装置) ceramic(陶瓷) textile(织物) detail_crop(某画的局部放大) sketch(未完成草稿涂鸦) low_quality(模糊/低清/噪点/损坏) non_art(截图/书页/纯文字/水印图/照片非艺术) empty(空白) other_artwork(其它艺术品)",\n'
'"quality":{"clarity":0到1清晰度,"integrity":0到1完整度(完整作品非局部/裁切),"merit":0到1展出价值(艺术价值与代表性,是否值得挂上美术馆)},\n'
'"identify":{"artist":"识别作者(确信是知名画作才填中文名,不确定留空字符串别瞎猜)","title":"作品名(同样不确定留空)","known":true或false,"confidence":0到1},\n'
'"worldview":{"wv":"世界观从6选1: WV1摹写之眼(忠实再现·客观格物) WV2礼制图式(神圣象征·程式秩序) WV3写意寄情(气韵心境·不求形似) WV4经验之光(瞬间光色·感官鲜活) WV5表现外化(情感张力·主观变形) WV6形式建构(抽象·结构·自指)","x":0到1(再现0↔表现1),"y":0到1(底层结构0↔即时感知1)},\n'
'"media":"①媒介/工艺,如 布面油画/纸本水彩",\n'
'"subject":"②画面题材:肖像/风景/静物/叙事/宗教/神话/风俗/抽象等",\n'
'"subject_tags":["②题材关键词2-4个,用于挂题材库"],\n'
'"style":{"流派":"主导流派","审美倾向":"","表现特征":""},\n'
'"style_mix":[{"流派":"流派名","pct":百分比数字}],\n'
'"reading":{"focus_top3":[{"what":"视觉重心","where":"位置","why":"为何吸睛"}],"path":"阅读路径 从…→…→…","guide":"引导手段","elements":["画面关键元素"]},\n'
'"objects":["③画面包含的具体物体,按画面占比从大到小罗列"],\n'
'"language7":{"构图与组织":{"desc":"技法+现象","v":0到1},"形状与造型":{"desc":"","v":0到1},"透视与空间":{"desc":"","v":0到1},"色彩系统":{"desc":"","v":0到1},"笔触与肌理":{"desc":"","v":0到1},"边缘与节奏":{"desc":"","v":0到1},"光影与明暗":{"desc":"","v":0到1}},\n'
'"affect":{"vad":{"valence":0到1,"arousal":0到1,"dominance":0到1},'
f'"primary_anchor":"从14锚点选1: {ANCHORS}",'
'"channels":{"构图姿态":"构图/姿态/视线如何推动情绪","题材语义":"题材或符号的情绪含义","光色":"光与色的情绪"},'
'"evidence":["情绪判断2-3条依据"],"confidence":0到1},\n'
'"allegory":"⑦寓意/象征总结:克制,只基于画面证据,不臆造",\n'
'"voiceover":"⑥画外音:一句有意象但不矫情的旁白",\n'
'"fused":"把以上各维串成一条不分段的长句自然语言画面描述"\n'
"}\n"
"category 判定从严:画的局部放大=detail_crop;雕塑/器物的翻拍照=sculpture/artifact(不是 painting);模糊低清=low_quality。"
"identify 只在确信认出知名画作时填 artist/title,否则留空别猜;style_mix 各项 pct 合计约100;objects 按面积从大到小;"
"language7 的 v=该视觉语言在画面里的明显程度;VAD 基于画面证据、勿只看颜色。")

# 提示词可在线编辑:存在 gate_prompt.txt 覆盖文件则用它,否则用内置 GATE_PROMPT。
PROMPT_FILE = os.path.join(os.path.dirname(__file__), "gate_prompt.txt")
def effective_prompt():
    try:
        if os.path.exists(PROMPT_FILE):
            t = open(PROMPT_FILE, encoding="utf-8").read().strip()
            if t: return t
    except Exception: pass
    return GATE_PROMPT
ACTIVE_PROMPT = GATE_PROMPT   # vlm() 启动时刷新为 effective_prompt()

def _parse_json(txt):
    i, j = txt.find("{"), txt.rfind("}")
    if i < 0 or j < 0: return None
    s = txt[i:j+1]
    for cand in (s, re.sub(r",\s*([}\]])", r"\1", s)):
        try: return json.loads(cand)
        except Exception: pass
    return None

def _vlm_call(base, key, model, b64, max_tokens=7500, timeout=340):
    msg = [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
        {"type": "text", "text": ACTIVE_PROMPT}]}]
    body = json.dumps({"model": model, "max_tokens": max_tokens, "messages": msg}).encode()
    req = urllib.request.Request(base, data=body, method="POST", headers={
        "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    txt = " ".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text").strip()
    return _parse_json(txt)

def _img_b64(cos_key, max_px):
    raw = cos().get_object(Bucket=SRC_BUCKET, Key=cos_key)["Body"].get_raw_stream().read()
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((max_px, max_px))
    bf = io.BytesIO(); im.save(bf, "JPEG", quality=85)
    return base64.b64encode(bf.getvalue()).decode()

def _review_one(args):
    work_id, cos_key, base, key, model, max_px = args
    try:
        b64 = _img_b64(cos_key, max_px)
    except Exception as e:
        return (work_id, None, f"img:{repr(e)[:60]}")
    last = "vlm_parse_fail"
    for attempt in range(2):          # 瞬时失败(网络/限流/坏JSON)重试1次,把 ~9% err 压到 ~1%
        try:
            v = _vlm_call(base, key, model, b64)
            if v: return (work_id, v, None)
        except Exception as e:
            last = repr(e)[:80]
        time.sleep(1.5 * (attempt + 1))
    return (work_id, None, last)

# 客观分辨率闸:min-side < MIN_SIDE 的图不进核心资产、也不送 VLM(省预算),直接软归档 low_res。
# 缘由:低分辨率名画缩略图 VLM 仍给高 merit,但在带放大的画廊里没法看。可用 AHA_MIN_SIDE 调。
MIN_SIDE = int(os.environ.get('AHA_MIN_SIDE', '600'))

def vlm(batch=None, limit=None, workers=6, max_px=768, source=None):
    global ACTIVE_PROMPT; ACTIVE_PROMPT = effective_prompt()
    base, key, model = mimo_cfg()
    conn = pg_conn(); cur = conn.cursor()
    where = "WHERE w.status='pending' AND f.file_id=w.primary_file_id"
    args = []
    if batch: where += " AND w.source_batch=%s"; args.append(batch)
    elif source: where += " AND w.source_batch LIKE %s"; args.append(source + "%")
    # 预闸:把本批 pending 里低于分辨率下限的直接软归档,不浪费 VLM
    cur.execute(f"""UPDATE works w SET status='archived', reject_reason='low_res', reviewed_at=now()
                    FROM files f WHERE {where[6:]}
                    AND least(f.width,f.height) < %s""", args + [MIN_SIDE])
    if cur.rowcount:
        print(f"[vlm] 分辨率预闸:{cur.rowcount} 张 <{MIN_SIDE}px 已软归档(low_res),跳过 VLM")
    conn.commit()
    where += " AND least(f.width,f.height) >= %s"; args = args + [MIN_SIDE]
    q = f"SELECT w.work_id, f.cos_key, f.width, f.height FROM works w JOIN files f ON f.file_id=w.primary_file_id {where} ORDER BY w.work_id"
    if limit: q += f" LIMIT {int(limit)}"
    cur.execute(q, args)
    todo = cur.fetchall()
    PX = {r[0]: (r[2], r[3]) for r in todo}      # work_id -> (w,h) 算分辨率分
    print(f"[vlm] {len(todo)} 张待审 (workers={workers}, max_px={max_px})")

    wlock = threading.Lock()
    n_keep = n_rej = n_err = 0
    t0 = time.time()
    tasks = [(wid, ck, base, key, model, max_px) for wid, ck, _w, _h in todo]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_review_one, t) for t in tasks]
        for done, fut in enumerate(as_completed(futs), 1):
            work_id, v, err = fut.result()
            with wlock:
                c = conn.cursor()
                if err:
                    n_err += 1
                    c.execute("UPDATE works SET reviewed_at=now(), reject_reason=%s WHERE work_id=%s",
                              (f"err:{err}", work_id))   # 留 pending,可重跑
                else:
                    m = re.match(r"[a-z_]+", (v.get("category") or "").strip().lower())
                    cat = m.group(0) if m else ""
                    status = cat_to_status(cat)
                    # 质量分标准:0.35·展出价值 + 0.25·清晰 + 0.15·完整 + 0.25·分辨率(客观,由宽高算)
                    qd = v.get("quality")
                    def _f(x):
                        try: return max(0.0, min(1.0, float(x)))
                        except Exception: return 0.0
                    if isinstance(qd, dict):
                        w_, h_ = PX.get(work_id, (None, None))
                        res = min(1.0, min(w_, h_) / 1500.0) if (w_ and h_) else 0.0
                        qual = round(0.35*_f(qd.get("merit")) + 0.25*_f(qd.get("clarity"))
                                     + 0.15*_f(qd.get("integrity")) + 0.25*res, 3)
                        v["quality_resolution"] = round(res, 3); v["quality_composite"] = qual
                    else:
                        try: qual = float(qd)
                        except Exception: qual = None
                    wvd = v.get("worldview")          # 归一 wv 到纯 WV1-6
                    if isinstance(wvd, dict):
                        mw = re.search(r"WV[1-6]", str(wvd.get("wv") or ""))
                        if mw: wvd["wv"] = mw.group(0)
                    is_art = status in ("kept", "archived")
                    rr = None if status == "kept" else cat   # archived/rejected 都把分类落进 reject_reason 便于筛
                    if status == "kept": n_keep += 1
                    else: n_rej += 1                          # 含 archived,见 stats 细分
                    c.execute("""UPDATE works SET status=%s, reject_reason=%s, quality=%s,
                                 is_artwork=%s, vlm=%s, reviewed_at=now() WHERE work_id=%s""",
                              (status, rr, qual, is_art, Json(v), work_id))
                conn.commit()
            if done % 25 == 0:
                sp = time.time() - t0
                print(f"  {done}/{len(todo)}  keep={n_keep} reject={n_rej} err={n_err}  {done/sp:.2f}张/s")
    print(f"[vlm] 完成 keep={n_keep} reject={n_rej} err={n_err}  用时{time.time()-t0:.0f}s")
    conn.close()

# ====================================================================
# stats
# ====================================================================
def stats(batch=None, reject_list=30):
    conn = pg_conn(); cur = conn.cursor()
    bw = "WHERE source_batch=%s" if batch else ""
    ba = [batch] if batch else []
    cur.execute(f"SELECT status, count(*) FROM works {bw} GROUP BY status ORDER BY 2 DESC", ba)
    print("=== 状态分布 ===")
    for s, c in cur.fetchall(): print(f"  {s:<10} {c}")
    cur.execute(f"""SELECT status, reject_reason, count(*) FROM works
                    WHERE status IN ('rejected','archived') {'AND source_batch=%s' if batch else ''}
                    GROUP BY status, reject_reason ORDER BY status, 3 DESC""", ba)
    print("=== rejected / archived 分类(category) ===")
    for s, r, c in cur.fetchall(): print(f"  [{s:<8}] {str(r):<16} {c}")
    if reject_list:
        cur.execute(f"""SELECT w.title, a.name_en, w.reject_reason, w.quality, f.cos_key
                        FROM works w JOIN artists a ON a.artist_id=w.artist_id
                        JOIN files f ON f.file_id=w.primary_file_id
                        WHERE w.status IN ('rejected','dup') {'AND w.source_batch=%s' if batch else ''}
                        ORDER BY w.reviewed_at DESC NULLS LAST LIMIT {int(reject_list)}""", ba)
        print(f"=== 最近被剔 {reject_list} 条(抽查 VLM 判得准不准) ===")
        for t, a, rr, q, ck in cur.fetchall():
            print(f"  [{str(rr):<12}] q={q} {a} — {str(t)[:40]}  | {ck}")
    cur.execute(f"""SELECT round(avg(quality)::numeric,3), count(*) FROM works
                    WHERE status='kept' {'AND source_batch=%s' if batch else ''}""", ba)
    r = cur.fetchone()
    print(f"=== 核心资产(kept):{r[1]} 件,平均质量 {r[0]} ===")
    conn.close()

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("dedup"); p.add_argument("--batch"); p.add_argument("--threshold", type=int, default=6)
    p = sub.add_parser("vlm"); p.add_argument("--batch"); p.add_argument("--source"); p.add_argument("--limit", type=int)
    p.add_argument("--workers", type=int, default=6); p.add_argument("--max-px", type=int, default=768)
    p = sub.add_parser("stats"); p.add_argument("--batch"); p.add_argument("--reject-list", type=int, default=30)
    a = ap.parse_args()
    if a.cmd == "dedup": dedup(a.batch, a.threshold)
    elif a.cmd == "vlm": vlm(a.batch, a.limit, a.workers, a.max_px, a.source)
    elif a.cmd == "stats": stats(a.batch, a.reject_list)

if __name__ == "__main__":
    main()
