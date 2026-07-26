#!/usr/bin/env python3
"""从造物云 API 提取模型信息，写入 gen_run.params.model。
用法: python3 extract_models.py [--workers 6] [--limit N]
"""
import os, json, time, argparse, urllib.request, ssl, socket
from concurrent.futures import ThreadPoolExecutor, as_completed
import psycopg2

socket.setdefaulttimeout(30)
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

TOKEN = "sk-DYZfTj8acrqtOYmlMj4C8qSbgiAbcIHEuJCh17BbH2XQQlGJ"
API_BASE = "https://app.zaowuyun.com"

def _cfg(p): return json.load(open(os.path.expanduser(p)))

def pg():
    d = _cfg("~/.aha_pg.json")
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

def extract_model_from_tasks(tasks):
    """从 tasks 中提取模型名称"""
    for t in tasks:
        tt = t.get("taskType", "")
        tin = t.get("inputData") or {}

        # third_party_api: endpoint 就是模型
        if tt.startswith("third_party_api:"):
            endpoint = tin.get("endpoint", "")
            if endpoint:
                # fal-ai/nano-banana/edit -> nano-banana
                parts = endpoint.split("/")
                if len(parts) >= 2:
                    return parts[-2] if parts[-1] in ("edit", "generate", "subscribe") else parts[-1]
                return endpoint

        # llm: model 字段
        if tt.startswith("llm:"):
            model = tin.get("model", "")
            if model:
                return model

        # comfyui: 从参数提取
        if tt.startswith("comfyui:"):
            # 检查常见的模型字段
            for key in ["31_model_type", "2_type"]:
                val = tin.get(key, "")
                if val and isinstance(val, str) and len(val) < 50:
                    return val
            # 检查 checkpoint
            for key in ["52_ckpt_name", "4_ckpt_name"]:
                val = tin.get(key, "")
                if val and isinstance(val, str):
                    # 提取模型名: SDXL/sd_xl_base_1.0_0.9vae.safetensors -> SDXL
                    if "/" in val:
                        return val.split("/")[0]
                    return val.replace(".safetensors", "").replace(".ckpt", "")[:50]
            # 检查 unet
            for key in ["37_unet_name", "1_unet_name"]:
                val = tin.get(key, "")
                if val and isinstance(val, str):
                    return val.replace(".safetensors", "")[:50]
            # 检查 workflow 名
            wf = tin.get("workflow", "")
            if wf:
                return f"comfyui:{wf[:30]}"

        # jimeng/ark
        if "jimeng" in tt or "ark" in tt:
            return "jimeng"

    return None

def process_one(instance_id):
    """处理单条记录"""
    try:
        req = urllib.request.Request(f"{API_BASE}/api/workflow/executions/{instance_id}",
                                    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
        resp = json.loads(urllib.request.urlopen(req, timeout=30, context=_SSL).read())
        data = resp.get("data", {})
        tasks = data.get("tasks", [])
        model = extract_model_from_tasks(tasks)
        return model
    except:
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    cn = pg()
    cur = cn.cursor()

    # 找出没有 model 的记录
    cur.execute("""SELECT instance_id FROM gen_run
                   WHERE source='zaowuyun_team' AND status='COMPLETED'
                   AND (params->>'model' IS NULL OR params->>'model' = '')
                   ORDER BY start_time DESC""")
    rows = cur.fetchall()
    cur.close()
    cn.close()

    if a.limit:
        rows = rows[:a.limit]

    print(f"待处理: {len(rows)} 条")

    t0 = time.time()
    n_done = n_found = 0

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(process_one, r[0]): r[0] for r in rows}
        for fut in as_completed(futs):
            iid = futs[fut]
            n_done += 1
            try:
                model = fut.result()
                if model:
                    n_found += 1
                    # 更新数据库
                    cn = pg()
                    cur = cn.cursor()
                    cur.execute("UPDATE gen_run SET params = jsonb_set(COALESCE(params, '{}'::jsonb), '{model}', %s) WHERE instance_id = %s",
                                (json.dumps(model), iid))
                    cn.commit()
                    cur.close()
                    cn.close()
            except:
                pass

            if n_done % 100 == 0:
                elapsed = time.time() - t0
                rate = n_done / elapsed if elapsed > 0 else 0
                print(f"  {n_done}/{len(rows)} done, {n_found} found, {rate:.1f}/s", flush=True)

    elapsed = time.time() - t0
    print(f"\n完成! {n_done} 条, {n_found} 有模型信息, 用时 {elapsed:.0f}s")

if __name__ == "__main__":
    main()
