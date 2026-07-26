#!/usr/bin/env python3
"""每日同步造物云「创意设计」团队新数据。
从 zaowuyun API 拉取最近 N 天的执行记录 → gen_run + gen_file。
幂等设计，可重复运行。

工作流来源 = 动态枚举:
  GET /api/workflow/metadata?limit=500 列出该团队当前【全部】工作流(~149个)。
  不再硬编码 workflow 清单 —— 新建的工作流会被自动覆盖,不会漏抓。
  (历史上曾硬编码 52 个,导致 28 个有执行的工作流共 222 次执行从未进库。)

只覆盖 token 绑定的「创意设计」团队(teamId 67ee23b636ff1d9725e06306);
跨客户团队需各自的 token,本脚本不处理。

用法:
  python3 sync_zwy_daily.py [--days 3] [--workers 6]
  python3 sync_zwy_daily.py --all         # 忽略天数,全量回扫(首次补漏用)
  python3 sync_zwy_daily.py --list        # 只打印当前工作流清单,不抓取
"""
import os, json, io, time, hashlib, argparse, threading, urllib.request, ssl, socket
from concurrent.futures import ThreadPoolExecutor, as_completed
socket.setdefaulttimeout(60)
import imagehash
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED = True
Image.MAX_IMAGE_PIXELS = None
from qcloud_cos import CosS3Client, CosConfig
import psycopg2

API_BASE = "https://app.zaowuyun.com"
TOKEN = "sk-DYZfTj8acrqtOYmlMj4C8qSbgiAbcIHEuJCh17BbH2XQQlGJ"
BUCKET = "aha-1254041526"
COS_PREFIX = "artworks/_generated/zaowuyun/"
SOURCE = "zaowuyun_team"

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

def _cfg(p): return json.load(open(os.path.expanduser(p)))

def _wf_name(w):
    """displayName 可能是字符串,也可能是 {'zh-CN':..,'en-US':..}。"""
    dn = w.get("displayName")
    if isinstance(dn, dict):
        return dn.get("zh-CN") or dn.get("en-US") or next(iter(dn.values()), "") or "(无名工作流)"
    return dn or "(无名工作流)"

def list_workflows():
    """动态枚举「创意设计」团队当前全部工作流 → {id: 名称}。
    metadata 默认只返回 24 条,必须带 limit 拿全量(~149)。"""
    req = urllib.request.Request(f"{API_BASE}/api/workflow/metadata?page=1&limit=500",
                                 headers={"Authorization": f"Bearer {TOKEN}"})
    data = json.loads(_retry_urlopen(req))
    rows = data.get("data") if isinstance(data, dict) else data
    out = {}
    for w in rows or []:
        if w.get("isDeleted"):
            continue
        wid = w.get("id") or w.get("workflowId")
        if wid:
            out[wid] = _wf_name(w)
    return out

_tls = threading.local()
def cos():
    if not hasattr(_tls, "cl"):
        c = _cfg("~/.aha_cos.json")
        _tls.cl = CosS3Client(CosConfig(Region=c["region"], SecretId=c["secret_id"], SecretKey=c["secret_key"], Timeout=30))
    return _tls.cl

def pg():
    d = _cfg("~/.aha_pg.json")
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

def _retry_urlopen(req, timeout=30, retries=5):
    for attempt in range(retries):
        try:
            return urllib.request.urlopen(req, timeout=timeout).read()
        except urllib.error.HTTPError as e:
            if e.code >= 500 and attempt < retries - 1:
                time.sleep(min(2**attempt, 15))
                continue
            raise
        except (TimeoutError, OSError, socket.timeout) as e:
            if attempt < retries - 1:
                time.sleep(min(2**attempt, 15))
                continue
            raise

def api_search(wf_id, page, limit=20):
    body = json.dumps({"workflowId": wf_id, "pagination": {"page": page, "limit": limit},
                        "orderBy": {"field": "startTime", "order": "DESC"}}).encode()
    req = urllib.request.Request(f"{API_BASE}/api/workflow/executions/search", data=body,
                                headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    return json.loads(_retry_urlopen(req))["data"]

def api_detail(instance_id):
    req = urllib.request.Request(f"{API_BASE}/api/workflow/executions/{instance_id}",
                                headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    return json.loads(_retry_urlopen(req))["data"]

def extract_meta(it, wf_name):
    inp = it.get("input") or {}
    out = it.get("output") or {}
    tasks = it.get("tasks") or []
    input_prompt = None
    candidates = []
    for k, v in inp.items():
        if k == "__context": continue
        if isinstance(v, str) and len(v) > 10 and not v.startswith("http"):
            candidates.append((len(v), v))
    if candidates:
        candidates.sort(reverse=True)
        input_prompt = candidates[0][1]
    output_images = []
    if isinstance(out, dict):
        for key in ("data", "file_list"):
            data_list = out.get(key, [])
            if isinstance(data_list, list):
                output_images.extend(u for u in data_list if isinstance(u, str) and "http" in u)
    output_images = list(dict.fromkeys(output_images))
    input_images = []
    for k, v in inp.items():
        if k == "__context": continue
        if isinstance(v, str) and "http" in v:
            input_images.append(v)
    model = None
    params = {}
    for t in tasks:
        tt = t.get("taskType") or ""
        t_input = t.get("inputData") or {}
        if "openai" in tt or "gpt" in tt:
            if "model" in t_input: model = t_input["model"]
        if "comfyui" in tt:
            for pk in ("seed", "steps", "cfg", "sampler_name", "scheduler", "width", "height"):
                if pk in t_input: params[pk] = t_input[pk]
    ctx = inp.get("__context", {})
    group = ctx.get("group", "")
    return {"input_prompt": input_prompt, "model": model,
            "params": {**params, "group": group} if params else ({"group": group} if group else {}),
            "output_images": output_images, "input_images": input_images}

def fetch_img(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=30, context=_SSL).read()
    sha = hashlib.sha256(raw).hexdigest()
    ext = url.rsplit(".", 1)[-1].split("?")[0].lower()
    if ext not in ("png", "jpg", "jpeg", "webp"): ext = "png"
    return raw, sha, ext

def process_image(url, wf_name, instance_id, cur, cn):
    try:
        raw, sha, ext = fetch_img(url)
        cur.execute("SELECT cos_key FROM gen_file WHERE sha256=%s LIMIT 1", (sha,))
        if cur.fetchone(): return True
        im = Image.open(io.BytesIO(raw)); im.load()
        w, h = im.size
        ph = str(imagehash.phash(im.convert("RGB")))
        cos_key = f"{COS_PREFIX}{wf_name}/{sha}.{ext}"
        cos().put_object(Bucket=BUCKET, Key=cos_key, Body=raw)
        cur.execute("""INSERT INTO gen_file (instance_id, cos_key, src_url, sha256, phash, width, height, bytes, fmt, role, source, q_status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'output', %s, 'pending')
                       ON CONFLICT (cos_key) DO NOTHING""",
                    (instance_id, cos_key, url, sha, ph, w, h, len(raw), ext, SOURCE))
        return True
    except:
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="拉取最近 N 天的数据")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--all", action="store_true", help="忽略天数,全量回扫(首次补漏)")
    ap.add_argument("--list", action="store_true", help="只打印当前工作流清单,不抓取")
    a = ap.parse_args()

    # 动态枚举团队当前全部工作流
    workflows = list_workflows()
    print(f"工作流(动态枚举): {len(workflows)} 个")
    if a.list:
        for wid, nm in workflows.items():
            print(f"  {wid}  {nm}")
        return

    cn = pg()
    cn.autocommit = False
    cur = cn.cursor()

    # 已存在的 instance_id
    cur.execute(f"SELECT instance_id FROM gen_run WHERE source='{SOURCE}'")
    existing = set(r[0] for r in cur.fetchall())
    print(f"已有 {len(existing)} 条记录")

    total_new = total_img = 0
    t0 = time.time()

    for wf_id, wf_name in workflows.items():
        d = api_search(wf_id, 1, 1)
        total = d.get("total", 0)
        if total == 0: continue

        page = 1
        page_size = 20
        consecutive_old = 0

        while True:
            d = api_search(wf_id, page, page_size)
            items = d.get("data", [])
            if not items: break

            for it in items:
                instance_id = it.get("workflowId", "")
                if not instance_id: continue

                # 检查是否超过 N 天(--all 时不按天截断,扫到底)
                start_time = it.get("startTime")
                if start_time and not a.all:
                    from datetime import datetime, timedelta, timezone
                    ts = datetime.fromtimestamp(start_time/1000, tz=timezone.utc)
                    cutoff = datetime.now(timezone.utc) - timedelta(days=a.days)
                    if ts < cutoff:
                        consecutive_old += 1
                        if consecutive_old > 50:
                            break
                        continue

                if instance_id in existing:
                    continue

                consecutive_old = 0
                status = it.get("status", "")
                meta = extract_meta(it, wf_name)

                try:
                    cur.execute("""INSERT INTO gen_run (instance_id, workflow_id, workflow_name, status,
                        input_prompt, input_images, params, start_time, end_time, raw, source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, to_timestamp(%s/1000.0), to_timestamp(%s/1000.0), %s, %s)
                        ON CONFLICT (instance_id) DO NOTHING""",
                        (instance_id, wf_id, wf_name, status,
                         meta["input_prompt"], json.dumps(meta["input_images"]) if meta["input_images"] else None,
                         json.dumps(meta["params"]) if meta["params"] else None,
                         start_time, it.get("endTime"),
                         json.dumps({"tasks_n": len(it.get("tasks", [])), "model": meta["model"]}),
                         SOURCE))
                    cn.commit()
                    existing.add(instance_id)
                    total_new += 1

                    img_urls = meta["output_images"]
                    if img_urls:
                        for url in img_urls:
                            if process_image(url, wf_name, instance_id, cur, cn):
                                total_img += 1
                        cn.commit()
                except Exception as e:
                    cn.rollback()

            if consecutive_old > 50: break
            page += 1
            time.sleep(0.3)

    elapsed = time.time() - t0
    print(f"\n同步完成! 新增 {total_new} 条, {total_img} 张图, 用时 {elapsed:.0f}s")
    cur.close()
    cn.close()

if __name__ == "__main__":
    main()
