#!/usr/bin/env python3
"""给生成图补 V2 十二维审美标注(worldview/language7/affect),写 gen_file.vlm_v2。
这是「美学竞技场 → 审美档案」的桥:有了它,结论卡能出真·门派/本命画家,arena 选择也能喂进推荐口味空间。
复用油画 gate.py 同一个 mimo-v2.5 端点与取图方式;只跑 arena 资格池;断点续(WHERE vlm_v2 IS NULL)。
注意:此 V2 prompt 直接给 language7 + affect.vad(12 维里的 10 维);worldview.x/y 需另一步 refill,缺则该 2 维留空(work_vec 会掩码)。

用法: python3 gen_vlm_v2.py --limit 20 --workers 4     # 小样本
      python3 gen_vlm_v2.py --limit 99999 --workers 6  # 全量(贵,慎用)
      python3 gen_vlm_v2.py --stats
"""
import json, os, io, time, base64, argparse, urllib.request, urllib.parse
import psycopg2
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

def _cfg(p): return json.load(open(os.path.expanduser(p)))
CC = _cfg("~/.aha_cos.json"); BUCKET = "aha-1254041526"
COS_HOST = f"{BUCKET}.cos.{CC['region']}.myqcloud.com"
def pg():
    d = _cfg("~/.aha_pg.json")
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])
def mimo_cfg():
    m = _cfg("~/.aha_mimo.json"); base = m["endpoint"].rstrip("/")
    if not base.endswith("/messages"): base += "/v1/messages"
    return base, m["key"], m["model"]

SCOPE = ("gf.role='output' AND gf.q_status<>'rejected' "
         "AND (r.source IS NULL OR (r.source='zaowuyun_team' AND gf.category LIKE 'art/%%'))")

ANCHORS = "喜悦 鲜活 热烈 崇高 张力 恐惧 神秘 忧伤 孤独 怀旧 虚无 沉思 平静 空灵"
PROMPT = ("预设你是一位艺术界大师 + 情绪分析师。看这张画,做'系统描述',只输出一个 JSON(不要解释/不要代码块):\n"
"{\n"
'"subject":"画面题材:肖像/风景/花卉/叙事等",\n'
'"style":{"流派":"","审美倾向":"","表现特征":""},\n'
'"language7":{\n'
'  "构图与组织":{"desc":"技法+现象","v":明显程度0到1},\n'
'  "形状与造型":{"desc":"","v":0到1},\n'
'  "透视与空间":{"desc":"","v":0到1},\n'
'  "色彩系统":{"desc":"","v":0到1},\n'
'  "笔触与肌理":{"desc":"","v":0到1},\n'
'  "边缘与节奏":{"desc":"","v":0到1},\n'
'  "光影与明暗":{"desc":"","v":0到1}},\n'
'"affect":{"vad":{"valence":0到1,"arousal":0到1,"dominance":0到1},'
f'"primary_anchor":"从14锚点选1: {ANCHORS}",'
'"evidence":["情绪判断的3条关键依据"],"confidence":0到1}\n'
"}\n"
"language7 的 v=该视觉语言在画面里的明显程度。VAD 基于画面证据、勿只看颜色。")

def thumb_b64(cos_key, px=768):
    url = f"https://{COS_HOST}/" + urllib.parse.quote(cos_key) + f"?imageMogr2/thumbnail/{px}x"
    raw = urllib.request.urlopen(url, timeout=60).read()
    im = Image.open(io.BytesIO(raw)).convert("RGB"); im.thumbnail((px, px))
    bf = io.BytesIO(); im.save(bf, "JPEG", quality=85)
    return base64.b64encode(bf.getvalue()).decode()

def call(base, key, model, b64, max_tokens=4000, timeout=300):
    msg = [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
        {"type": "text", "text": PROMPT}]}]
    body = json.dumps({"model": model, "max_tokens": max_tokens, "messages": msg}).encode()
    req = urllib.request.Request(base, data=body, method="POST",
                                headers={"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    return ' '.join(b.get('text', '') for b in out.get('content', []) if b.get('type') == 'text').strip()

def parse(txt):
    i = txt.find('{'); j = txt.rfind('}')
    if i < 0 or j < 0: return None
    import re
    s = txt[i:j + 1]
    try: return json.loads(s)
    except Exception:
        try: return json.loads(re.sub(r',\s*}', '}', re.sub(r',\s*]', ']', s)))
        except Exception: return None

def fetch_todo(cur, limit):
    cur.execute(f"""SELECT gf.cos_key FROM gen_file gf JOIN gen_run r ON r.instance_id=gf.instance_id
                    WHERE {SCOPE} AND gf.vlm_v2 IS NULL
                    ORDER BY gf.q_status='kept' DESC, random() LIMIT %s""", (limit,))
    return [x[0] for x in cur.fetchall()]

def one(base, key, model, cos_key):
    try:
        b64 = thumb_b64(cos_key)
        v2 = parse(call(base, key, model, b64))
        if not v2 or "language7" not in v2: return (cos_key, None, "no-language7")
        return (cos_key, v2, None)
    except Exception as e:
        return (cos_key, None, str(e)[:80])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    cn = pg(); cur = cn.cursor()
    if a.stats:
        cur.execute(f"SELECT count(*) FILTER(WHERE gf.vlm_v2 IS NOT NULL), count(*) FROM gen_file gf JOIN gen_run r ON r.instance_id=gf.instance_id WHERE {SCOPE}")
        done, tot = cur.fetchone(); print(f"vlm_v2 已标注 {done} / 资格池 {tot}"); return
    base, key, model = mimo_cfg()
    todo = fetch_todo(cur, a.limit)
    print(f"待标注 {len(todo)} 张 · workers={a.workers}", flush=True)
    ok = err = 0; t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(one, base, key, model, k) for k in todo]
        for i, f in enumerate(as_completed(futs), 1):
            cos_key, v2, e = f.result()
            if v2:
                cur.execute("UPDATE gen_file SET vlm_v2=%s WHERE cos_key=%s", (json.dumps(v2, ensure_ascii=False), cos_key)); cn.commit(); ok += 1
            else:
                err += 1
            if i % 5 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} ok={ok} err={err} {i/(time.time()-t0):.2f} img/s", flush=True)
    print(f"完成 ok={ok} err={err} 用时 {time.time()-t0:.0f}s", flush=True)
    cn.close()

if __name__ == "__main__":
    main()
