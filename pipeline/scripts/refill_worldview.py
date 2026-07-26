#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定向补世界观坐标:给"有 language7/VAD 但缺 worldview"的真作品补 worldview{wv,x,y}。
背景:早期"合并 VLM 批"用的提示词不含世界观,导致这些作品落不到世界观平面。
用最小"只问世界观"的提示词重读图(快&省),把结果 MERGE 进 vlm(不动已有 language7/affect)。
默认只处理 canon 艺术家的作品。并发。幂等(只补缺的)。

用法: python3 refill_worldview.py [--limit N] [--all-artists] [--workers 6]
"""
import os, io, sys, json, time, base64, urllib.request, threading, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate  # 复用 cos()/pg_conn/mimo_cfg/_parse_json/SRC_BUCKET + PIL
from PIL import Image
import psycopg2.extras

WV_PROMPT = (
"看这幅画,只判断它在「世界观平面」上的位置。两根正交轴:X=再现(0)↔表现(1)[忠于眼睛所见 vs 忠于内心所感];"
"Y=底层结构(0)↔即时感知(1)[构造秩序/可读图式 vs 感官光色的即时印象]。六区参考:"
"WV1摹写之眼(忠实再现) WV2礼制图式(神圣象征·程式) WV3写意寄情(气韵心境) "
"WV4经验之光(瞬间光色) WV5表现外化(情感张力·主观变形) WV6形式建构(抽象·结构)。"
'只输出 JSON,无多余文字:{"wv":"WV1到WV6择一","x":0到1,"y":0到1}')

def _vlm_wv(base, key, model, b64, max_tokens=2000, timeout=180):
    msg = [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
        {"type": "text", "text": WV_PROMPT}]}]
    body = json.dumps({"model": model, "max_tokens": max_tokens, "messages": msg}).encode()
    req = urllib.request.Request(base, data=body, method="POST", headers={
        "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    txt = " ".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text").strip()
    return gate._parse_json(txt)

import re as _re
def one(args):
    wid, cos_key = args
    try:
        b64 = gate._img_b64(cos_key, 768)
        base, key, model = gate.mimo_cfg()
        d = _vlm_wv(base, key, model, b64)
        if not d: return (wid, None)
        wv = (_re.search(r"WV[1-6]", str(d.get("wv") or "")) or [None])
        x = d.get("x"); y = d.get("y")
        if x is None or y is None: return (wid, None)
        return (wid, {"wv": (wv.group(0) if hasattr(wv, "group") else d.get("wv")),
                      "x": round(float(x), 3), "y": round(float(y), 3)})
    except Exception as e:
        return (wid, None)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--all-artists", action="store_true", help="不限 canon,补全库缺世界观的")
    a = ap.parse_args()
    cn = gate.pg_conn(); cur = cn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    where = "w.vlm ? 'language7' AND w.vlm->'worldview'->>'x' IS NULL AND w.status='kept'"
    if not a.all_artists: where += " AND a.aha_kg_id IS NOT NULL"
    lim = f"LIMIT {a.limit}" if a.limit else ""
    cur.execute(f"""SELECT w.work_id, f.cos_key FROM works w JOIN artists a ON a.artist_id=w.artist_id
                    JOIN files f ON f.file_id=w.primary_file_id WHERE {where}
                    ORDER BY w.quality DESC NULLS LAST {lim}""")
    rows = [(r["work_id"], r["cos_key"]) for r in cur.fetchall()]
    print(f"[refill_worldview] 待补 {len(rows)} 件{'(全库)' if a.all_artists else '(canon)'}")
    ok = 0; fail = 0; done = 0
    wcur = cn.cursor()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(one, r) for r in rows]
        for f in as_completed(futs):
            wid, wv = f.result(); done += 1
            if wv:
                wcur.execute("UPDATE works SET vlm = jsonb_set(coalesce(vlm,'{}'::jsonb), '{worldview}', %s::jsonb, true) WHERE work_id=%s",
                             (json.dumps(wv), wid))
                ok += 1
                if ok % 20 == 0: cn.commit()
            else:
                fail += 1
            if done % 25 == 0: print(f"  ...{done}/{len(rows)} (补 {ok} 失 {fail})")
    cn.commit(); cn.close()
    print(f"✓ 补世界观 {ok} 件 / 失败 {fail} / 共 {len(rows)}")

if __name__ == "__main__":
    main()
