#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把会展出的英文作品标题翻译成中文(中文为主,英文留作副)。
存 work_edit.title(最高优先;原英文 works.title 仍在=副)。mimo 批量。可重跑增量。
用法: python3 translate_titles.py [--limit N] [--batch 30] [--apply]   默认 dry-run 只看不写。"""
import os, re, json, argparse, urllib.request, psycopg2
from psycopg2.extras import execute_values

def cfg(p): return json.load(open(os.path.expanduser(p)))
def mimo():
    m = cfg("~/.aha_mimo.json"); base = m["endpoint"].rstrip("/")
    if not base.endswith("/messages"): base += "/v1/messages"
    return base, m["key"], m["model"]
d = cfg("~/.aha_pg.json")
con = psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"]); cur = con.cursor()
BASE, KEY, MODEL = mimo()

PROMPT = """你是艺术品著录专家。把下列油画的英文标题翻译成简洁、地道、符合艺术史习惯的中文标题。
要求:只译标题本身,保留人名/地名等专有名词的通用中文译名;不要加引号、书名号、解释或编号;
人物肖像可用「…肖像」「…的画像」。逐条对应,返回纯 JSON 数组(字符串),顺序与输入完全一致,长度相同。
输入(JSON数组):
%s"""

def translate(titles):
    body = json.dumps({"model": MODEL, "max_tokens": 8000,
        "messages": [{"role": "user", "content": [{"type": "text", "text": PROMPT % json.dumps(titles, ensure_ascii=False)}]}]}).encode()
    req = urllib.request.Request(BASE, data=body, method="POST",
        headers={"content-type": "application/json", "x-api-key": KEY, "anthropic-version": "2023-06-01"})
    r = json.load(urllib.request.urlopen(req, timeout=300))
    txt = "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
    m = re.search(r"\[.*\]", txt, re.S)
    arr = json.loads(m.group(0)) if m else None
    return arr if (arr and len(arr) == len(titles)) else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60); ap.add_argument("--batch", type=int, default=30)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    # 优先:会展出的(kept 或 高清非归档)、纯英文标题、尚无中文编辑
    cur.execute("""SELECT v.work_id, v.title FROM v_ledger v
        LEFT JOIN work_edit we ON we.work_id=v.work_id
        WHERE v.title ~ '[A-Za-z]' AND v.title !~ '[一-鿿]'
          AND (v.status='kept' OR (v.res_tier='hd' AND v.status<>'archived'))
          AND we.title IS NULL
        ORDER BY (v.status='kept') DESC, v.px DESC NULLS LAST LIMIT %s""", (a.limit,))
    rows = cur.fetchall()
    nb = (len(rows)+a.batch-1)//a.batch
    print(f"待翻译(优先展出层) {len(rows)} 条 / {nb} 批", flush=True)
    total = 0
    for i in range(0, len(rows), a.batch):
        chunk = rows[i:i+a.batch]
        try: zh = translate([t for _, t in chunk])
        except Exception as e: print(f"  批{i//a.batch+1} 异常 {str(e)[:50]}", flush=True); continue
        if not zh:
            print(f"  批{i//a.batch+1} 翻译失败,跳过", flush=True); continue
        batch_done = [(wid, cn.strip()) for (wid, en), cn in zip(chunk, zh)
                      if cn and re.search(r'[一-鿿]', cn.strip())]
        if a.apply and batch_done:
            execute_values(cur, """INSERT INTO work_edit(work_id,title,edited_by) VALUES %s
                ON CONFLICT(work_id) DO UPDATE SET title=EXCLUDED.title,edited_by='translate',edited_at=now()""",
                [(wid, cn, "translate") for wid, cn in batch_done])
            con.commit()
        total += len(batch_done)
        ex = chunk[0][1][:28]
        print(f"  批{i//a.batch+1}/{nb}: +{len(batch_done)} (累计{total})  例「{ex}」→「{batch_done[0][1] if batch_done else '?'}」", flush=True)
    print(f"\n{'✓ 已写入' if a.apply else '[dry-run]'} work_edit 累计 {total} 条(中文为主,英文 works.title 留副)")

if __name__ == "__main__":
    main()
