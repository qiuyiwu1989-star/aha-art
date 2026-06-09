#!/usr/bin/env python3
"""aha 出图代理 — 把意图编译器的 prompt 转给火山方舟,密钥仅留服务端。
监听 127.0.0.1:8093,经 nginx /aha/api/ 反代。POST /generate {prompt,size?,negative?}。
轻量防滥用:每 IP 滑动窗口限流 + size 白名单 + prompt 长度上限。"""
import json, os, time, urllib.request, urllib.error, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CFG = json.load(open(os.path.expanduser('~/.aha_ark.json')))
KEY, MODEL, ENDPOINT = CFG['key'], CFG['model'], CFG['endpoint']
ADMIN_PASS = CFG.get('admin_pass', '')
try:
    MIMO = json.load(open(os.path.expanduser('~/.aha_mimo.json')))
except Exception:
    MIMO = None

COMPILE_SYS = """你是 aha 的艺术语义编译器:把用户模糊的灵感,沿生成因果链推理成一份可执行的绘画方案。
核心公式:风格 = 世界模型 × 感知策略 × 造型方法 × 语言参数 × 意义指向。
推理原则:
1. 世界观先行:风格是世界假设的外化,不是滤镜。
2. 双向扩散:从用户给的任意已知维度(题材/情绪/风格/艺术家),向空白维度推理补全。
3. 最小完整假设:缺的维度用最保守推断补,绝不臆造用户没暗示的文化背景或叙事。
4. 矛盾词保留张力(如"热烈的冷漠"),选能承载张力的风格,别化解。
5. 策略A=语义扩散(给词/感受);策略D=艺术家基因(给艺术家名,解其世界观/语言/色彩/情绪再按需重组)。
铁律(必须遵守):
- **style_id 只能从我给你的候选 candidates 里选**,严禁发明候选外的风格;style_cn 必须与所选 style_id 一致。
- subject 题材尽量取候选风格的 subjects 或用户明确说的;anchor 取 14 锚点之一;motive 取 V1-V5。
- prompt 按七维有序写(构图→造型→空间→光影→色彩→笔触→边缘),120-200字自然语言,中文。
- negative 用该风格 avoid(负空间),写"不要画什么"。
- reasoning 用 2-3 句说清"为什么这么定"(扣世界观/情绪/题材)。
只输出 JSON,不要任何解释文字或 markdown 代码块标记。schema:
{"strategy":"A|D","reasoning":"...","directions":[{"style_id":"STYLE...","style_cn":"...","subject":"...","anchor":"...","motive":"V1","language_note":"...","prompt":"...","negative":"..."}]}
单个模糊输入给 2-3 个不同方向(directions);明确输入给 1 个。"""


def _extract_json(txt):
    i = txt.find('{')
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(txt)):
        if txt[j] == '{':
            depth += 1
        elif txt[j] == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(txt[i:j + 1])
                except Exception:
                    return None
    return None


VISION_SYS = """你是 aha 的艺术读图编译器:看一张画,沿生成因果链把它拆解,并映射到我给你的真实图谱节点上。
拆解维度:媒介 / 题材 / 风格观察 / 视觉重心与阅读路径 / 7大构成(构图造型空间光影色彩笔触边缘)/ 情绪。
铁律:
- closest_style_cn 与每个 direction 的 style_cn **只能从我给的 styles 列表里选**,严禁发明列表外的风格名。
- anchor 取我给的 anchors 之一;motive 取 V1-V5。
- 第 1 个 direction = "忠实重绘"(最接近原图风格);可再给 1-2 个"换风格重画"的方向(若用户给了 hint 就按 hint)。
- prompt 七维有序(构图→造型→空间→光影→色彩→笔触→边缘),120-200字中文;negative 写"不要画什么"。
只输出 JSON,无多余文字:
{"strategy":"C","reasoning":"...","analysis":{"媒介":"...","题材":"...","风格观察":"...","视觉重心":"...","情绪":"..."},"closest_style_cn":"...","directions":[{"style_cn":"...","subject":"...","anchor":"...","motive":"V1","prompt":"...","negative":"..."}]}"""


def llm_vision(payload):
    img = payload.get('image_b64') or ''
    mt = payload.get('media_type') or 'image/jpeg'
    styles = payload.get('styles') or []
    anchors = payload.get('anchors') or []
    hint = (payload.get('hint') or '').strip()
    txt = ("可选风格(只能从中选 style_cn):" + "、".join(styles[:210]) +
           "\n锚点:" + "、".join(anchors) +
           ("\n用户要求(换风格重画):" + hint if hint else "") +
           "\n请读图并按 schema 输出 JSON。")
    body = {"model": MIMO['model'], "max_tokens": 4000, "system": VISION_SYS,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mt, "data": img}},
                {"type": "text", "text": txt}]}]}
    req = urllib.request.Request(MIMO['endpoint'].rstrip('/') + '/v1/messages',
                                 data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json",
                                          "x-api-key": MIMO['key'],
                                          "anthropic-version": "2023-06-01"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    t = ''.join(b.get('text', '') for b in d.get('content', []) if b.get('type') == 'text')
    return _extract_json(t), t


WV_AXES = ("x轴 = 再现(0.0)→表现(1.0):越忠实摹写真实越接近0,越主观变形/抽象越接近1。"
           "y轴 = 结构(0.0)→感知(1.0):越重秩序/构成/理性越接近0,越重气氛/光色/瞬间感越接近1。")


COORDS_SYS = """你是世界观坐标测量器,给一幅画在两条轴上各打一个 0-1 的分。请先看清画,再对照下面的标杆刻度打分,不要凭空给数。

【x 轴 = 再现 → 表现】越忠实摹写真实=越小,越主观变形/抽象=越大。标杆:
  照相写实/古典写实≈0.10 · 学院写实/巴洛克写实≈0.30 · 印象派外光≈0.55 · 后印象/表现主义变形≈0.72 · 几乎纯抽象≈0.92
【y 轴 = 结构 → 感知】越重秩序/几何/理性构成=越小,越重气氛/光色/瞬间感=越大。标杆:
  古典素描/几何构成/极简硬边≈0.20 · 文艺复兴均衡构图≈0.40 · 一般写实场景≈0.55 · 印象光色弥漫≈0.85 · 睡莲式无轮廓弥漫≈0.93

步骤:① 先用一句话描述这幅画的造型/笔触/光色特征;② 对照标杆,分别定 x 和 y。
只输出 JSON,无多余文字:{"desc":"一句特征描述","x":0.xx,"y":0.xx,"note":"为什么是这个刻度"}"""


def llm_coords(img_b64, mt):
    sys = COORDS_SYS
    body = {"model": MIMO['model'], "max_tokens": 2000, "system": sys,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mt, "data": img_b64}},
                {"type": "text", "text": "给这幅画测两轴坐标。"}]}]}
    req = urllib.request.Request(MIMO['endpoint'].rstrip('/') + '/v1/messages',
                                 data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", "x-api-key": MIMO['key'],
                                          "anthropic-version": "2023-06-01"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    t = ''.join(b.get('text', '') for b in d.get('content', []) if b.get('type') == 'text')
    return _extract_json(t)


def _target_coord(style_id, style_cn):
    try:
        idx = json.load(open(WEBROOT + '/data/kg_compile_index_v2.json'))['styles']
        if style_id in idx:
            return idx[style_id].get('coord'), idx[style_id].get('wv')
        for sid, s in idx.items():
            if s.get('cn') == style_cn:
                return s.get('coord'), s.get('wv')
    except Exception:
        pass
    return None, None


def backtest_one(gid):
    import math
    with _glock:
        g = json.load(open(GALLERY))
    rec = next((x for x in g.get('items', []) if x.get('id') == gid), None)
    if not rec:
        raise ValueError('无此记录')
    img = open(WEBROOT + '/' + rec['file'], 'rb').read()
    b64 = __import__('base64').b64encode(img).decode()
    # 多次读数取平均,降低 LLM 目测噪声(单次抖动实测 ±0.08)
    reads = []
    note = ''
    for _ in range(3):
        c = llm_coords(b64, 'image/jpeg')
        if c and c.get('x') is not None:
            reads.append((float(c['x']), float(c['y'])))
            note = c.get('note', note) or note
    if not reads:
        raise ValueError('坐标读取失败')
    ax = sum(r[0] for r in reads) / len(reads)
    ay = sum(r[1] for r in reads) / len(reads)
    jitter = sum(math.hypot(r[0] - ax, r[1] - ay) for r in reads) / len(reads)
    tgt, twv = _target_coord(rec.get('style_id', ''), rec.get('style_cn', ''))
    out = {'actual_wv': {'x': round(ax, 3), 'y': round(ay, 3), 'note': note,
                         'n_reads': len(reads), 'jitter': round(jitter, 3)}}
    if tgt and tgt.get('x') is not None:
        tx, ty = float(tgt['x']), float(tgt['y'])
        out['target_wv'] = {'x': tx, 'y': ty}
        out['error'] = round(math.hypot(ax - tx, ay - ty), 3)
    out['ts_backtest'] = int(time.time())
    with _glock:
        g = json.load(open(GALLERY))
        for x in g['items']:
            if x.get('id') == gid:
                x['backtest'] = out
        tmp = GALLERY + '.tmp'
        json.dump(g, open(tmp, 'w'), ensure_ascii=False, indent=1)
        os.replace(tmp, GALLERY)
    return out


def llm_compile(payload):
    inp = (payload.get('input') or '')[:600]
    context = payload.get('context') or {}
    strategy = payload.get('strategy') or 'A'
    user = ("用户输入:" + inp + "\n策略:" + strategy +
            "\n\n候选节点(只能从中选 style_id;artist 仅供策略D解码):\n" +
            json.dumps(context, ensure_ascii=False)[:9000])
    body = {"model": MIMO['model'], "max_tokens": 4000, "system": COMPILE_SYS,
            "messages": [{"role": "user", "content": user}]}
    req = urllib.request.Request(MIMO['endpoint'].rstrip('/') + '/v1/messages',
                                 data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json",
                                          "x-api-key": MIMO['key'],
                                          "anthropic-version": "2023-06-01"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    txt = ''.join(b.get('text', '') for b in d.get('content', []) if b.get('type') == 'text')
    return _extract_json(txt), txt
SIZE_OK = {'1K', '2K', '1024x1024', '2048x2048'}
MAXLEN = 1500
RATE_N, RATE_WIN = 8, 60          # 每 IP 每 60s 最多 8 次
_hits = {}                         # ip -> [ts...]
_lock = threading.Lock()
_glock = threading.Lock()         # 图库写锁
WEBROOT = '/data/pub/p/aha'
IMGDIR = WEBROOT + '/img/gen'
GALLERY = WEBROOT + '/data/kg_gen_gallery.json'


def model_label(mid):
    try:
        for m in json.load(open(WEBROOT + '/data/kg_gen_models.json'))['models']:
            if m['id'] == mid:
                return m['label']
    except Exception:
        pass
    return mid or MODEL


def save_record(url, prompt, meta):
    """下载 TOS 图(24h 内有效)自托管 + 追加元数据。返回 web 相对路径。"""
    req = urllib.request.Request(url, headers={'User-Agent': 'aha-gen'})
    with urllib.request.urlopen(req, timeout=120) as r:
        img = r.read()
    if len(img) < 1000:
        raise ValueError('图太小,疑似失效')
    gid = '%d_%s' % (int(time.time()), os.urandom(3).hex())
    rel = 'img/gen/%s.jpg' % gid
    with open(WEBROOT + '/' + rel, 'wb') as f:
        f.write(img)
    m = meta or {}
    rec = {'id': gid, 'file': rel, 'prompt': prompt,
           'query': m.get('query', ''),
           'style_id': m.get('style_id', ''),
           'style_cn': m.get('style_cn', ''),
           'fields': m.get('fields', {}),
           'ts': int(time.time()),
           'model': m.get('model_id', 'seedream5'),
           'model_label': model_label(m.get('model_id', 'seedream5')),
           'set_id': m.get('set_id', ''),
           'rating': None,
           'bytes': len(img)}
    with _glock:
        try:
            g = json.load(open(GALLERY))
        except Exception:
            g = {'items': []}
        g.setdefault('items', []).insert(0, rec)
        tmp = GALLERY + '.tmp'
        json.dump(g, open(tmp, 'w'), ensure_ascii=False, indent=1)
        os.replace(tmp, GALLERY)
    return rec


def allowed(ip):
    now = time.time()
    with _lock:
        q = [t for t in _hits.get(ip, []) if now - t < RATE_WIN]
        if len(q) >= RATE_N:
            _hits[ip] = q
            return False
        q.append(now)
        _hits[ip] = q
        return True


def gen(prompt, size, negative):
    body = {
        "model": MODEL, "prompt": prompt,
        "sequential_image_generation": "disabled",
        "response_format": "url", "size": size or "2K",
        "stream": False, "watermark": False,
    }
    if negative:
        body["prompt"] = prompt + "。避免:" + negative
    data = json.dumps(body).encode()
    req = urllib.request.Request(ENDPOINT, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + KEY,
    }, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    url = (d.get("data") or [{}])[0].get("url")
    return url, d.get("model")


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip('/') in ('/health', '/generate'):
            return self._send(200, {"ok": True, "model": MODEL})
        self._send(404, {"error": "not found"})

    def _read(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n) or b'{}')

    def do_POST(self):
        route = self.path.rstrip('/')
        ip = self.headers.get('X-Real-IP') or self.client_address[0]
        if route == '/compile':
            if not MIMO:
                return self._send(503, {"error": "推理端点未配置"})
            if not allowed(ip):
                return self._send(429, {"error": "太频繁,请稍后再试"})
            try:
                p = self._read()
            except Exception:
                return self._send(400, {"error": "bad json"})
            if not (p.get('input') or '').strip():
                return self._send(400, {"error": "缺 input"})
            try:
                obj, raw = llm_compile(p)
                if not obj:
                    return self._send(502, {"error": "推理返回无法解析", "raw": raw[:300]})
                return self._send(200, {"card": obj})
            except urllib.error.HTTPError as e:
                return self._send(502, {"error": "推理上游 %d" % e.code, "detail": e.read().decode()[:200]})
            except Exception as e:
                return self._send(500, {"error": str(e)[:200]})
        if route == '/backtest':
            if not MIMO:
                return self._send(503, {"error": "推理端点未配置"})
            if not allowed(ip):
                return self._send(429, {"error": "太频繁,请稍后再试"})
            try:
                p = self._read()
            except Exception:
                return self._send(400, {"error": "bad json"})
            if not p.get('id'):
                return self._send(400, {"error": "缺 id"})
            try:
                return self._send(200, {"ok": True, "backtest": backtest_one(p['id'])})
            except Exception as e:
                return self._send(502, {"error": str(e)[:200]})
        if route == '/rate':
            try:
                p = self._read()
            except Exception:
                return self._send(400, {"error": "bad json"})
            gid = p.get('id')
            if not gid:
                return self._send(400, {"error": "缺 id"})
            with _glock:
                try:
                    g = json.load(open(GALLERY))
                except Exception:
                    g = {'items': []}
                rec = next((x for x in g.get('items', []) if x.get('id') == gid), None)
                if not rec:
                    return self._send(404, {"error": "无此记录"})
                rec['rating'] = p.get('rating')
                tmp = GALLERY + '.tmp'
                json.dump(g, open(tmp, 'w'), ensure_ascii=False, indent=1)
                os.replace(tmp, GALLERY)
            return self._send(200, {"ok": True, "rating": rec['rating']})
        if route == '/vision':
            if not MIMO:
                return self._send(503, {"error": "推理端点未配置"})
            if not allowed(ip):
                return self._send(429, {"error": "太频繁,请稍后再试"})
            try:
                p = self._read()
            except Exception:
                return self._send(400, {"error": "bad json"})
            if not p.get('image_b64'):
                return self._send(400, {"error": "缺图"})
            try:
                obj, raw = llm_vision(p)
                if not obj:
                    return self._send(502, {"error": "读图返回无法解析", "raw": raw[:300]})
                return self._send(200, {"card": obj})
            except urllib.error.HTTPError as e:
                return self._send(502, {"error": "读图上游 %d" % e.code, "detail": e.read().decode()[:200]})
            except Exception as e:
                return self._send(500, {"error": str(e)[:200]})
        if route == '/delete':
            try:
                p = self._read()
            except Exception:
                return self._send(400, {"error": "bad json"})
            if not ADMIN_PASS or p.get('pass') != ADMIN_PASS:
                return self._send(403, {"error": "口令错误"})
            gid = p.get('id')
            if not gid:
                return self._send(400, {"error": "缺 id"})
            with _glock:
                try:
                    g = json.load(open(GALLERY))
                except Exception:
                    g = {'items': []}
                items = g.get('items', [])
                rec = next((x for x in items if x.get('id') == gid), None)
                if not rec:
                    return self._send(404, {"error": "无此记录"})
                try:
                    fp = WEBROOT + '/' + rec['file']
                    if os.path.exists(fp):
                        os.remove(fp)
                except Exception:
                    pass
                g['items'] = [x for x in items if x.get('id') != gid]
                tmp = GALLERY + '.tmp'
                json.dump(g, open(tmp, 'w'), ensure_ascii=False, indent=1)
                os.replace(tmp, GALLERY)
            return self._send(200, {"ok": True, "remaining": len(g['items'])})
        if route == '/save':
            try:
                p = self._read()
            except Exception:
                return self._send(400, {"error": "bad json"})
            if not p.get('url'):
                return self._send(400, {"error": "缺 url"})
            try:
                rec = save_record(p['url'], (p.get('prompt') or '')[:MAXLEN], p.get('meta'))
                return self._send(200, {"ok": True, "id": rec['id'], "file": rec['file']})
            except Exception as e:
                return self._send(502, {"error": "保存失败:" + str(e)[:200]})
        if route != '/generate':
            return self._send(404, {"error": "not found"})
        if not allowed(ip):
            return self._send(429, {"error": "太频繁,请稍后再试(每分钟最多 8 张)"})
        try:
            payload = self._read()
        except Exception:
            return self._send(400, {"error": "bad json"})
        prompt = (payload.get('prompt') or '').strip()
        if not prompt:
            return self._send(400, {"error": "缺 prompt"})
        if len(prompt) > MAXLEN:
            prompt = prompt[:MAXLEN]
        size = payload.get('size') if payload.get('size') in SIZE_OK else '2K'
        try:
            url, model = gen(prompt, size, payload.get('negative'))
            if not url:
                return self._send(502, {"error": "上游无图返回"})
            # 自动保存:出图即落库(TOS 链 24h 失效,趁新鲜自托管)
            saved = {}
            try:
                rec = save_record(url, prompt, payload.get('meta'))
                saved = {"file": rec['file'], "id": rec['id'], "saved": True}
            except Exception as se:
                saved = {"saved": False, "save_error": str(se)[:120]}
            self._send(200, dict({"url": url, "model": model}, **saved))
        except urllib.error.HTTPError as e:
            self._send(502, {"error": "上游错误 %d" % e.code, "detail": e.read().decode()[:300]})
        except Exception as e:
            self._send(500, {"error": str(e)[:200]})

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    srv = ThreadingHTTPServer(('127.0.0.1', 8093), H)
    print("aha ark gen proxy on 127.0.0.1:8093")
    srv.serve_forever()
