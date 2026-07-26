#!/usr/bin/env python3
"""造物云新团队(67ee23b636ff1d9725e06306)AI生成数据全量入库。
从 app.zaowuyun.com API 拉取执行记录 → gen_run / gen_file → COS artworks/_generated/zaowuyun/。

用法:
  python3 ingest_zwy_gen.py [--limit N] [--workers 6] [--workflow NAME]
"""
import os, sys, json, io, time, hashlib, argparse, threading, urllib.request, ssl, socket
from concurrent.futures import ThreadPoolExecutor, as_completed
os.environ.setdefault('MODELSCOPE_CACHE', os.path.expanduser('~/.cache/modelscope'))
socket.setdefaulttimeout(30)  # 全局 socket 超时
import imagehash
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None
from qcloud_cos import CosS3Client, CosConfig
import psycopg2

# ── 配置 ──
API_BASE = "https://app.zaowuyun.com"
TOKEN = "sk-DYZfTj8acrqtOYmlMj4C8qSbgiAbcIHEuJCh17BbH2XQQlGJ"
TEAM_ID = "67ee23b636ff1d9725e06306"
BUCKET = "aha-1254041526"
COS_PREFIX = "artworks/_generated/zaowuyun/"
SOURCE = "zaowuyun_team"

# 74 个工作流 ID → 中文名
WORKFLOWS = {
    "686ddecb7715878e4a684bb8": "CAKA-文生图-图生图",
    "6870b72ccf143c9faeb4cedf": "CAKA文生文",
    "6879f7dbe33626d54a0bbecd": "CAKA-图生文",
    "68b66527eaeb6e7177398c40": "CAKA多图融合",
    "6808afafd3be77e3689bf5c2": "飞书-多图生单图",
    "6821ba45ee9f7dd30beb6998": "花型四方连续",
    "6821b13f0fdbaad81a0e7d2b": "文本生成成衣",
    "6821b8352ebfdd0566dc7019": "花型生成花型（单图）",
    "6821bb3eaefc49be7ef83595": "花型智能扩图",
    "6821beb3d1b712d995258f03": "成衣提取花型",
    "6821bf97295b01cdaee5379e": "文本生成花型",
    "6821bffed0fa1672745afd6b": "成衣全局改款",
    "6821c27da2a04b5cc604e9eb": "成衣局部改款(无参考图)",
    "6822af44b8a0343a68bcfac5": "成衣风格融合",
    "6822b190704a5d3ad110f435": "成衣智能配色",
    "6822b2d23deb833d68dda98e": "线稿生成成衣",
    "6822b4dddb873e3dc5d1d3e6": "成衣提取线稿",
    "6822b5a9802bd2b7f088a016": "成衣生成多视角",
    "6822b92004601823622a797e": "成衣任意模特上身",
    "6822c126905188287610dffd": "替换背景",
    "6822c073a9bdf73bfd15936d": "成衣渲染模特",
    "6822c24eff9591479ae23dbf": "光影大片",
    "6822c30570de07bb0e2d286a": "智能抠图",
    "6822dc22d0419d59395b7d98": "图片去水印",
    "6822e843b879dfbd4583f25e": "花型生成成衣",
    "6822eb0d0f65ea6789a908c6": "成衣指定模特上身",
    "6822edc47d656198b6f92a42": "花型生成花型（多图）",
    "6822ff6112021af18c218266": "成衣特定姿势上身",
    "6822f4bb98db68b7e9af040e": "成衣风格融合",
    "6823086c005c28b2306fba3a": "成衣局部改款（有参考图）",
    "68089fca16621784445d7eb8": "单文生多图",
    "6808b0a7667896bf66bd3c1a": "单图+多图生多图",
    "6808c74f317d9d9da760b658": "多图生多图（多批次）",
    "6809d1f0a668016aaea368ce": "单文生单图",
    "6809d1bdb58be572dd1517a8": "单图生单图",
    "68a57062220e6f46938e0b43": "图片放大4倍",
    "6825d7cca9196e9ec51d1e4c": "线稿转效果图",
    "6825d8b4541eb15a6eb9a5e7": "4o工作流",
    "682d3c16e8ece72df245c052": "万物皆可钻",
    "686e8539eedfb4c2c17fec78": "wan21姿势控制视频",
    "67f8dfcf9109dd6733b3b6ab": "潘多拉手链挂件批量生成",
    "67f9190af5eeced4405ad7b6": "4o图片编辑",
    "67f8e01e934d7ab805fe2e25": "毛绒图标",
    "67f9199d90efe13173f8ba11": "4o图片编辑v1",
    "67f919d19635536069b64ba1": "4o图片编辑v1",
    "67fb52170d59e586f37b9a11": "袋装包装",
    "67f4e64da6376c12a3b95f9a": "Instant照片换脸",
    "6801c93ee94968a7b744cc19": "4o工作流",
    "6801e5a3451e7dd1eca3f2cd": "4o杂交工作流",
    "6808a4388ebd55795de02996": "单图生多图",
    "6821b7363f62ce685b19c5fa": "单图单文生成单文",
    "68242fd05428e4d246f3a3cf": "文本生成产品",
    "68254dd846537103dc0ee2b8": "CMF产品融合",
    "68249ea1fb6da07b7f1fc9ac": "CMF智能配色",
    "682495a507f69bd163882a83": "线稿生成产品",
    "6824982cdf73a74971d426c8": "产品风格融合",
    "68248de71cd49f27d9b535c6": "产品局部改款（有参考图）",
    "6824787359821d0e730153ce": "产品局部改款(无参考图)",
    "682453a1e711ba078418739c": "产品全局改款",
    "68255f02774aa468463ac9a6": "包装设计",
    "68256063ce066675172d87f1": "产品提取线稿",
    "682561c7cef628c23ecaac45": "产品生成多视角",
    "682563b74efe6b7651ae166d": "产品光影大片",
    "6825657758f588487d3999c9": "产品替换背景",
    "6825996ec6ced73bb88ed28e": "文本生成图片",
    "682599e9645bc7f21f0bb71a": "图片生成图片",
    "68259be6f7af4e3643294773": "图标设计",
    "68259c72a1234d75f38f144e": "排字设计",
    "68259da4882d726c8ea31432": "海报设计",
    "68259e19f0614df879ef9f54": "剧照编辑",
    "6825a0b5e7e67c1cfff6918a": "路演图片编辑",
    "6825a04018b259e01aa8dff2": "现场工作照编辑",
    "68259f7d9be831563017fbde": "人物定妆照编辑",
}

# ── 基础设施 ──
def _cfg(p): return json.load(open(os.path.expanduser(p)))
_cc = _cfg("~/.aha_cos.json")
def cos_client(): return CosS3Client(CosConfig(Region=_cc["region"], SecretId=_cc["secret_id"], SecretKey=_cc["secret_key"], Timeout=30))
_tls = threading.local()
def cos():
    if not hasattr(_tls, "cl"): _tls.cl = cos_client()
    return _tls.cl

def pg():
    d = _cfg("~/.aha_pg.json")
    return psycopg2.connect(host=d["host"], port=d["port"], dbname=d["dbname"], user=d["user"], password=d["password"])

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

# ── API 调用 ──
def _retry_urlopen(req, timeout=30, retries=8):
    """带重试的 HTTP 请求，处理 500/502/503/504 等服务端错误"""
    for attempt in range(retries):
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return resp.read()
        except urllib.error.HTTPError as e:
            if e.code >= 500 and attempt < retries - 1:
                wait = min(2 ** attempt, 30)
                print(f"    [retry {attempt+1}/{retries}] HTTP {e.code}, 等 {wait}s 重试...", flush=True)
                time.sleep(wait)
                continue
            raise
        except (TimeoutError, OSError, socket.timeout, ConnectionResetError) as e:
            if attempt < retries - 1:
                wait = min(2 ** attempt, 30)
                print(f"    [retry {attempt+1}/{retries}] {e}, 等 {wait}s 重试...", flush=True)
                time.sleep(wait)
                continue
            raise

def api_search(wf_id, page, limit=20):
    body = json.dumps({
        "workflowId": wf_id,
        "pagination": {"page": page, "limit": limit},
        "orderBy": {"field": "startTime", "order": "DESC"}
    }).encode()
    req = urllib.request.Request(f"{API_BASE}/api/workflow/executions/search", data=body,
                                headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    resp = json.loads(_retry_urlopen(req))
    return resp["data"]

def api_detail(instance_id):
    req = urllib.request.Request(f"{API_BASE}/api/workflow/executions/{instance_id}",
                                headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    resp = json.loads(_retry_urlopen(req))
    return resp["data"]

# ── 元数据提取 ──
def extract_meta(it, wf_name):
    """从执行记录提取元数据"""
    inp = it.get("input") or {}
    out = it.get("output") or {}
    tasks = it.get("tasks") or []

    # 提示词: 优先找最长的非URL文本字段
    input_prompt = None
    candidates = []
    for k, v in inp.items():
        if k == "__context": continue
        if isinstance(v, str) and len(v) > 10 and not v.startswith("http"):
            candidates.append((len(v), v))
    if candidates:
        candidates.sort(reverse=True)
        input_prompt = candidates[0][1]

    # 输出图
    output_images = []
    if isinstance(out, dict):
        data_list = out.get("data", [])
        if isinstance(data_list, list):
            output_images = [u for u in data_list if isinstance(u, str) and "http" in u]

    # 输入图
    input_images = []
    for k, v in inp.items():
        if k == "__context": continue
        if isinstance(v, str) and "http" in v:
            input_images.append(v)

    # 模型/参数: 从 tasks 提取
    model = None
    params = {}
    for t in tasks:
        tt = t.get("taskType") or ""
        t_input = t.get("inputData") or {}
        # openai_gpt4_vision 任务包含模型信息
        if "openai" in tt or "gpt" in tt:
            if "model" in t_input:
                model = t_input["model"]
            for pk in ("model", "size", "quality", "style", "temperature"):
                if pk in t_input:
                    params[pk] = t_input[pk]
        # comfyui 任务包含生成参数
        if "comfyui" in tt:
            for pk in ("seed", "steps", "cfg", "sampler_name", "scheduler", "width", "height"):
                if pk in t_input:
                    params[pk] = t_input[pk]

    # 从 input context 提取更多信息
    ctx = inp.get("__context", {})
    group = ctx.get("group", "")

    return {
        "input_prompt": input_prompt,
        "model": model,
        "params": {**params, "group": group} if params else ({"group": group} if group else {}),
        "output_images": output_images,
        "input_images": input_images,
    }

# ── 图片处理 ──
def fetch_img(url):
    """下载图片，返回 (bytes, sha256, ext)"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=30, context=_SSL).read()
    sha = hashlib.sha256(raw).hexdigest()
    ext = url.rsplit(".", 1)[-1].split("?")[0].lower()
    if ext not in ("png", "jpg", "jpeg", "webp"): ext = "png"
    return raw, sha, ext

def process_image(url, wf_name, instance_id, cur, cn):
    """下载图片 → 上传 COS → 插入 gen_file。返回 True/False。"""
    try:
        raw, sha, ext = fetch_img(url)

        # 检查是否已存在
        cur.execute("SELECT cos_key FROM gen_file WHERE sha256=%s LIMIT 1", (sha,))
        row = cur.fetchone()
        if row: return True  # 已存在，跳过

        # 获取图片信息
        im = Image.open(io.BytesIO(raw))
        im.load()
        w, h = im.size
        ph = str(imagehash.phash(im.convert("RGB")))

        # 上传 COS
        cos_key = f"{COS_PREFIX}{wf_name}/{sha}.{ext}"
        cos().put_object(Bucket=BUCKET, Key=cos_key, Body=raw)

        # 插入 gen_file
        cur.execute("""INSERT INTO gen_file (instance_id, cos_key, src_url, sha256, phash, width, height, bytes, fmt, role, source, q_status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'output', %s, 'pending')
                       ON CONFLICT (cos_key) DO NOTHING""",
                    (instance_id, cos_key, url, sha, ph, w, h, len(raw), ext, SOURCE))
        return True
    except Exception as e:
        return False

# ── 主流程 ──
def run_workflow(wf_id, wf_name, limit, workers, existing_ids, pg_cur, pg_cn):
    """处理单个工作流的所有执行记录"""
    # 获取总数
    d = api_search(wf_id, 1, 1)
    total = d.get("total", 0)
    if total == 0:
        return 0, 0, 0

    print(f"  [{wf_name}] total={total}", flush=True)

    n_run = n_img = n_skip = 0
    page = 1
    page_size = 20
    consecutive_skips = 0

    while True:
        d = api_search(wf_id, page, page_size)
        items = d.get("data", [])
        if not items:
            break

        # 每 50 页打印一次进度（含 skip 计数）
        if page % 50 == 0:
            print(f"    page {page}: {n_run} runs, {n_img} imgs, skip={n_skip}", flush=True)

        time.sleep(0.3)  # 限速，避免 API 500

        for it in items:
            if limit and n_run >= limit:
                break

            instance_id = it.get("workflowId", "")

            if not instance_id:
                continue

            # 幂等检查
            if instance_id in existing_ids:
                n_skip += 1
                consecutive_skips += 1
                continue

            consecutive_skips = 0
            status = it.get("status", "")
            start_time = it.get("startTime")
            end_time = it.get("endTime")

            # 提取元数据
            meta = extract_meta(it, wf_name)

            # 插入 gen_run
            try:
                pg_cur.execute("""INSERT INTO gen_run (instance_id, workflow_id, workflow_name, status,
                    input_prompt, input_images, params, start_time, end_time, raw, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, to_timestamp(%s/1000.0), to_timestamp(%s/1000.0), %s, %s)
                    ON CONFLICT (instance_id) DO NOTHING""",
                    (instance_id, wf_id, wf_name, status,
                     meta["input_prompt"], json.dumps(meta["input_images"]) if meta["input_images"] else None,
                     json.dumps(meta["params"]) if meta["params"] else None,
                     start_time, end_time,
                     json.dumps({"tasks_n": len(it.get("tasks", [])), "model": meta["model"]}),
                     SOURCE))
                pg_cn.commit()
                existing_ids.add(instance_id)
                n_run += 1
            except Exception as e:
                pg_cn.rollback()
                continue

            # 处理输出图片(并发)
            img_urls = meta["output_images"]
            if img_urls:
                with ThreadPoolExecutor(max_workers=min(4, len(img_urls))) as img_ex:
                    futs = {img_ex.submit(process_image, u, wf_name, instance_id, pg_cur, pg_cn): u for u in img_urls}
                    for fut in as_completed(futs):
                        if fut.result():
                            n_img += 1
                pg_cn.commit()

            if (n_run + n_skip) % 500 == 0:
                print(f"    {n_run} runs, {n_img} imgs, skip={n_skip}", flush=True)

        if limit and n_run >= limit:
            break
        page += 1

    return n_run, n_img, n_skip

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="每个工作流最多处理N条")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--workflow", type=str, help="只处理指定工作流名")
    a = ap.parse_args()

    cn = pg()
    cn.autocommit = False
    cur = cn.cursor()

    # 加载已存在的 instance_id（用于去重）
    cur.execute(f"SELECT instance_id FROM gen_run WHERE source='{SOURCE}'")
    existing_ids = set(r[0] for r in cur.fetchall())
    print(f"已有 {len(existing_ids)} 条记录", flush=True)

    workflows = WORKFLOWS
    if a.workflow:
        workflows = {k: v for k, v in WORKFLOWS.items() if v == a.workflow}
        if not workflows:
            print(f"未找到工作流: {a.workflow}")
            return

    total_runs = total_imgs = total_skips = 0
    t0 = time.time()

    for wf_id, wf_name in workflows.items():
        try:
            nr, ni, ns = run_workflow(wf_id, wf_name, a.limit, a.workers, existing_ids, cur, cn)
            total_runs += nr
            total_imgs += ni
            total_skips += ns
            print(f"  => {wf_name}: runs={nr} imgs={ni} skip={ns}", flush=True)
        except Exception as e:
            print(f"  !! {wf_name}: {e}", flush=True)
            cn.rollback()

    elapsed = time.time() - t0
    print(f"\n>>> 完成 runs={total_runs} imgs={total_imgs} skip={total_skips} 用时{elapsed:.0f}s", flush=True)
    cn.close()

if __name__ == "__main__":
    main()
