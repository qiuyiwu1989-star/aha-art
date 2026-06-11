#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""frame_curate.py — 逐画装裱策展(根治"关键词→框太粗")。
让 LLM 读每幅画已有的 VLM 深读(题材/主体标签/流派审美/媒材/年代/作者/情绪/fused 描述),
从框目录 mu_frame_style 的 8 种框里挑「最配这幅画」的一种 + 表面色调建议 + 理由 + 置信,
写回 works.vlm->'frame'。这是「建议层」:前端优先级 = 人工馆方指定 > LLM建议 > 关键词auto。
真实调用 mimo(禁 mock)。文本调用(用已有 VLM 读图结果,不重新看图,省钱省时)。

用法:
  python3 scripts/frame_curate.py --sample 8         # 抽样(含花卉静物)看质量
  python3 scripts/frame_curate.py --limit 50         # 跑前 50(未策展的优先)
  python3 scripts/frame_curate.py --all --workers 6  # 全量 exhibited
  python3 scripts/frame_curate.py --ids <work_id> ...
  --redo 连已策展过的也重判(默认跳过已有 vlm.frame.by='llm')
"""
import os, sys, io, json, re, time, argparse, threading, urllib.request
import psycopg2
from concurrent.futures import ThreadPoolExecutor, as_completed

def _cfg(p): return json.load(open(os.path.expanduser(p)))
def pg_conn():
    d = _cfg("~/.aha_pg.json")
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])
def mimo_cfg():
    m = _cfg("~/.aha_mimo.json"); base = m["endpoint"].rstrip("/")
    if not base.endswith("/messages"): base += "/v1/messages"
    return base, m["key"], m["model"]

def _parse_json(txt):
    if not txt: return None
    for cand in (txt, *re.findall(r"\{.*\}", txt, re.S)):
        try: return json.loads(cand)
        except Exception: pass
    return None

def load_frames(cur):
    cur.execute("SELECT key,name,descr,css_note,material FROM mu_frame_style WHERE active ORDER BY sort")
    return [{"key": k, "name": n, "descr": d, "css_note": c, "material": m} for k, n, d, c, m in cur.fetchall()]

SYS = """你是 aha 美术馆的资深装裱师(framing curator)。给你一幅画的深度解读资料和一套真实可采购的画框目录,
请像专业装裱师那样,为这幅画挑选**最合适的一种框**。

真实装裱的判断维度(综合权衡,不要只看流派标签):
- 时代与气质:古典/宗教/巴洛克/文艺复兴/学院派 → 描金雕花(庄重);19世纪写实/印象/浪漫油画 → 素木暖框或描金(看精致度);现当代/抽象 → 亚克力浮裱。
- 媒材:版画/素描/水彩/纸本 → 宽白卡;摄影 → 黑漆细框;东方水墨/工笔/绢本 → 卷轴朱漆。
- 题材与精致度:精致的花卉/静物/肖像/沙龙小品,即使标"现实主义",传统上也配描金或带金线的暖框,而非朴素素木;粗犷的社会写实/风景才配朴素素木。
- 色温:冷蓝绿调可配冷银;暖调配暖木/描金。
- 形制:留白多、东方意趣 → 卷轴。

只输出一个 JSON,不要任何多余文字:
{"frame":"<框的key>","finish":"<表面/颜色微调建议,如 暖金/深胡桃/哑光黑,一句话>","why":"<为什么配这个框,≤30字,具体到这幅画>","conf":<0~1 置信度>}"""

def build_user(w, frames):
    v = w["vlm"] or {}
    st = v.get("style") or {}
    parts = []
    if w.get("artist"): parts.append(f"作者:{w['artist']}")
    if w.get("year"): parts.append(f"年代:{w['year']}")
    if w.get("region"): parts.append(f"地区:{w['region']}")
    if v.get("subject"): parts.append(f"题材:{v['subject']}")
    if v.get("subject_tags"): parts.append("主体标签:" + "、".join(v["subject_tags"]) if isinstance(v["subject_tags"], list) else f"主体标签:{v['subject_tags']}")
    if isinstance(st, dict):
        s = "/".join(x for x in [st.get("流派"), st.get("审美倾向"), st.get("表现特征")] if x)
        if s: parts.append(f"风格:{s}")
    elif st: parts.append(f"风格:{st}")
    if v.get("media"): parts.append(f"媒材:{v['media']}")
    af = v.get("affect") or {}
    if isinstance(af, dict) and af.get("channels"):
        ch = af["channels"]; mood = ch.get("光色") or ch.get("题材语义") or ""
        if mood: parts.append(f"氛围:{mood}")
    if v.get("fused"): parts.append(f"画面综述:{v['fused']}")
    catalog = "\n".join(f'- {f["key"]}「{f["name"]}」:{f["descr"]}({f.get("css_note") or ""})' for f in frames)
    return f"""【这幅画】
{chr(10).join(parts)}

【可选画框目录(只能从这些 key 里选一个)】
{catalog}

请为这幅画挑最合适的一种框,按系统要求只输出 JSON。"""

def call_llm(base, key, model, sysmsg, usermsg, max_tokens=3000, timeout=200):
    body = json.dumps({"model": model, "max_tokens": max_tokens, "system": sysmsg,
                       "messages": [{"role": "user", "content": usermsg}]}).encode()
    req = urllib.request.Request(base, data=body, method="POST", headers={
        "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    txt = " ".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text").strip()
    return _parse_json(txt), txt

def curate_one(args):
    w, frames, base, key, model, valid = args
    user = build_user(w, frames)
    last = "parse_fail"
    for attempt in range(2):
        try:
            j, raw = call_llm(base, key, model, SYS, user)
            if j and j.get("frame") in valid:
                return (w["work_id"], {"key": j["frame"], "finish": (j.get("finish") or "")[:40],
                                       "why": (j.get("why") or "")[:60],
                                       "conf": _num(j.get("conf")), "by": "llm", "model": model}, None)
            last = "bad_frame:" + str(j.get("frame") if j else raw[:50])
        except Exception as e:
            last = repr(e)[:80]
        time.sleep(1.5 * (attempt + 1))
    return (w["work_id"], None, last)

def _num(x):
    try: return max(0.0, min(1.0, float(x)))
    except Exception: return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sample", type=int, default=0, help="跨题材抽样(含静物/花卉)看质量")
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--redo", action="store_true", help="连已策展过的也重判")
    a = ap.parse_args()
    base, key, model = mimo_cfg()
    conn = pg_conn(); cur = conn.cursor()
    frames = load_frames(cur); valid = {f["key"] for f in frames}
    print(f"[frame_curate] 框目录 {len(frames)} 种:{', '.join(sorted(valid))}")

    where = "w.exhibited AND w.vlm IS NOT NULL"
    args = []
    if a.ids:
        where += " AND w.work_id = ANY(%s)"; args.append([int(x) for x in a.ids])
    if not a.redo:
        where += " AND (w.vlm->'frame'->>'by') IS DISTINCT FROM 'llm'"  # NULL(未策展)也要纳入
    order = "w.work_id"
    if a.sample:
        # 抽样优先覆盖多题材(静物/花卉/肖像/风景/宗教/现代),用 subject_tags 散开
        order = "md5(w.work_id)"  # 伪随机但确定
    q = f"""SELECT w.work_id, w.title, a.name_cn, a.name_en, a.region, w.year, w.vlm
            FROM works w JOIN artists a ON a.artist_id=w.artist_id WHERE {where} ORDER BY {order}"""
    lim = a.sample or a.limit
    if lim and not a.ids: q += f" LIMIT {int(lim)}"
    cur.execute(q, args)
    rows = cur.fetchall()
    works = [{"work_id": r[0], "title": r[1], "artist": r[2] or r[3], "region": r[4], "year": r[5], "vlm": r[6]} for r in rows]
    print(f"[frame_curate] 待策展 {len(works)} 幅 (workers={a.workers}, model={model})")
    if not works: return

    tasks = [(w, frames, base, key, model, valid) for w in works]
    lock = threading.Lock(); n_ok = n_err = 0; t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(curate_one, t) for t in tasks]
        for i, fut in enumerate(as_completed(futs), 1):
            wid, fr, err = fut.result()
            with lock:
                c = conn.cursor()
                if fr:
                    c.execute("UPDATE works SET vlm = jsonb_set(coalesce(vlm,'{}'), '{frame}', %s::jsonb) WHERE work_id=%s",
                              (json.dumps(fr), wid)); conn.commit(); n_ok += 1
                    if a.sample or i <= 12:
                        t = next((w["title"] or w["artist"] for w in works if w["work_id"] == wid), wid)
                        print(f"  ✓ {str(t)[:26]:26} → {fr['key']:7} ({fr['finish']}) · {fr['why']} [conf {fr['conf']}]")
                else:
                    n_err += 1; print(f"  ✗ {wid}: {err}")
            if i % 50 == 0: print(f"  …{i}/{len(works)}  ok={n_ok} err={n_err}  {int(time.time()-t0)}s")
    print(f"[frame_curate] 完成 ok={n_ok} err={n_err} 用时 {int(time.time()-t0)}s")
    conn.close()

if __name__ == "__main__":
    main()
