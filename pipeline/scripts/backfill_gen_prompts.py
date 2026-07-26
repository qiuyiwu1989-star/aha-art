#!/usr/bin/env python3
"""补全 gen 数据中缺失的 prompt 和 metadata。
从 artist.infmonkeys.com API 拉取缺失的 input_prompt。
用法: python3 backfill_gen_prompts.py [--limit N]
"""
import os, json, time, argparse, urllib.request, ssl, socket, psycopg2

socket.setdefaulttimeout(30)
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

TOKEN = "sk-p47tZseNM3LhbY5CU7wFqhGuhJKqOMcz7yNQgn6R8kltktMU"
API_HOST = "artist.infmonkeys.com"
API_IP = "180.163.146.10"

# DNS 补丁：直接替换 URL 中的 host
import urllib.request as _urllib_orig
_orig_open = _urllib_orig.urlopen

def _patched_urlopen(req, timeout=None, **kw):
    if isinstance(req, _urllib_orig.Request):
        url = req.full_url
        if API_HOST in url:
            url = url.replace(API_HOST, API_IP)
            req = _urllib_orig.Request(url, data=req.data, headers=dict(req.headers))
            req.add_header('Host', API_HOST)
    if timeout is None:
        timeout = 30
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return _orig_open(req, timeout=timeout, context=ctx, **kw)

_urllib_orig.urlopen = _patched_urlopen

def _cfg(p): return json.load(open(os.path.expanduser(p)))

def pg():
    d = _cfg("~/.aha_pg.json")
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

def api_detail(instance_id, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(f"https://{API_HOST}/api/workflow/executions/{instance_id}",
                                        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=30).read())["data"]
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise

def extract_prompt(detail):
    """从 API 返回中提取 prompt"""
    inp = detail.get("input") or {}
    for k, v in inp.items():
        if k == "__context": continue
        if isinstance(v, str) and len(v) > 10 and not v.startswith("http"):
            return v
    return None

def extract_model(detail):
    """从 tasks 中提取模型名"""
    tasks = detail.get("tasks") or []
    for t in tasks:
        tt = t.get("taskType", "")
        tin = t.get("inputData") or {}
        if tt.startswith("third_party_api:"):
            endpoint = tin.get("endpoint", "")
            if endpoint:
                parts = endpoint.split("/")
                return parts[-2] if len(parts) >= 2 else parts[-1]
        if tt.startswith("llm:"):
            model = tin.get("model", "")
            if model: return model
        if tt.startswith("comfyui:"):
            for key in ["31_model_type", "2_type"]:
                val = tin.get(key, "")
                if val and isinstance(val, str) and len(val) < 50: return val
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="最多处理 N 条")
    a = ap.parse_args()

    cn = pg()
    cur = cn.cursor()

    # 找出没有 prompt 的 infmonkeys 记录
    cur.execute("""SELECT r.instance_id, r.workflow_name
                   FROM gen_run r JOIN gen_file gf ON r.instance_id=gf.instance_id
                   WHERE r.source IS NULL AND gf.role='output'
                   AND (r.input_prompt IS NULL OR r.input_prompt = '')
                   ORDER BY r.start_time DESC""")
    rows = cur.fetchall()
    print(f"没有 prompt 的 infmonkeys 记录: {len(rows)} 条")

    if a.limit:
        rows = rows[:a.limit]
        print(f"限制处理: {len(rows)} 条")

    n_done = n_filled = n_model = 0
    t0 = time.time()

    for iid, wf in rows:
        try:
            detail = api_detail(iid)
            prompt = extract_prompt(detail)
            model = extract_model(detail)

            if prompt:
                cur.execute("UPDATE gen_run SET input_prompt = %s WHERE instance_id = %s", (prompt, iid))
                n_filled += 1

            if model:
                cur.execute("UPDATE gen_run SET params = jsonb_set(COALESCE(params, '{}'::jsonb), '{model}', %s) WHERE instance_id = %s", (json.dumps(model), iid))
                n_model += 1

            cn.commit()
            n_done += 1
            time.sleep(0.5)  # 限速，避免 API 500

            if n_done % 100 == 0:
                elapsed = time.time() - t0
                rate = n_done / elapsed if elapsed > 0 else 0
                print(f"  {n_done}/{len(rows)} done, {n_filled} prompts, {n_model} models, {rate:.1f}/s", flush=True)

        except Exception as e:
            cn.rollback()
            n_done += 1
            if n_done <= 5:
                print(f"  ERROR: {str(e)[:80]}", flush=True)

    elapsed = time.time() - t0
    print(f"\n完成! {n_done} 条, {n_filled} prompt 补全, {n_model} model 补全, 用时 {elapsed:.0f}s")
    cur.close()
    cn.close()

if __name__ == "__main__":
    main()
