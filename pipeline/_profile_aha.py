#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aha 审美档案引擎 — 把用户行为(mu_event)投影成 12 维审美点云。

12 维 = worldview(2: 再现-表现 x / 结构-感知 y) + language7(7 轴 v 值) + affect.vad(3: v/a/d)
        —— 与 works.vlm 同构,所以"用户 μ = engaged 作品向量的加权均值",
        本命画家=艺术家质心里最近者,门派=6世界观区×8亚型,三盏灯/d* 自学习按 kg-me-algo。

可作模块被 ark_gen_server(8093) / catalog_api(8094) import,亦可 CLI:
  python3 profile.py --artists           重建艺术家质心 mu_artist_vec
  python3 profile.py --uid <uid>         算单个用户档案并入库
  python3 profile.py --all               重算所有有行为的用户
  python3 profile.py --foryou <uid>      打印为你推荐前 20
"""
import os, json, math, sys
import psycopg2
from psycopg2.extras import RealDictCursor

_PG = json.load(open(os.path.expanduser("~/.aha_pg.json")))
COS_BASE = "https://aha-1254041526.cos.ap-shanghai.myqcloud.com/"


def img_url(cos_key, thumb=None):
    """cos_key → 公网图 URL(demo226 本地图走 nginx 根;COS 图可加缩略)。"""
    if not cos_key:
        return None
    if cos_key.startswith("img/"):
        return "/" + cos_key
    from urllib.parse import quote
    u = COS_BASE + quote(cos_key, safe="/")
    return u + ("?imageMogr2/thumbnail/%dx" % thumb) if thumb else u


def _conn():
    return psycopg2.connect(host=_PG["host"], port=_PG["port"], dbname=_PG["dbname"],
                            user=_PG["user"], password=_PG["password"], connect_timeout=5)


# ---- 12 维定义 ----
# language7 在库里的中文长名 → kg-me 短名顺序(构图,空间,造型,光影,色彩,笔触,边缘)
LANG_KEYS = ["构图与组织", "透视与空间", "形状与造型", "光影与明暗", "色彩系统", "笔触与肌理", "边缘与节奏"]
DIM = 12  # wv_x, wv_y, lang*7, v, a, d

# 6 世界观区中心(再现-表现 x / 结构-感知 y),与 kg-worldview_v3 / me.html RG 一致
WV_REGIONS = [
    ("WV1", "摹写之眼", 0.232, 0.389), ("WV2", "礼制图式", 0.41, 0.287),
    ("WV3", "写意寄情", 0.528, 0.457), ("WV4", "经验之光", 0.533, 0.733),
    ("WV5", "表现外化", 0.775, 0.512), ("WV6", "形式建构", 0.82, 0.207),
]
SUBTYPE = {'111': '守炉人', '110': '深井者', '101': '移巢者', '100': '孤旅者',
           '011': '集萃者', '010': '博览家', '001': '漫游者', '000': '游牧者'}
SUBDESC = {'守炉人': '认定一种美,安守深耕', '深井者': '口味集中,越挖越深', '移巢者': '专注一种,隔阵子整体搬家',
           '孤旅者': '一次只爱一种,不断远行寻新', '集萃者': '兼收并蓄,围绕稳定中心', '博览家': '口味开阔,乐于尝鲜',
           '漫游者': '什么都看,随性而至', '游牧者': '又广又爱冒险,逐美而居'}
# 行为权重(与 museum EVENT_W 对齐)
EVENT_W = {'like': 3, 'collect': 3, 'dwell': 2, 'gen': 2, 'open': 1, 'view': 0.3, 'skip': -1}


def _f(x):
    try:
        v = float(x)
        return v if 0.0 <= v <= 1.0 else max(0.0, min(1.0, v))
    except Exception:
        return None


def work_vec(vlm):
    """从单件 vlm jsonb 取 12 维向量,缺失维度为 None(用掩码均值)。返回 list[12] 或 None(全缺)。"""
    if not vlm:
        return None
    v = [None] * DIM
    wv = vlm.get("worldview") or {}
    v[0] = _f(wv.get("x")); v[1] = _f(wv.get("y"))
    l7 = vlm.get("language7") or {}
    for i, k in enumerate(LANG_KEYS):
        cell = l7.get(k)
        if isinstance(cell, dict):
            v[2 + i] = _f(cell.get("v"))
        elif cell is not None:
            v[2 + i] = _f(cell)
    vad = (vlm.get("affect") or {}).get("vad") or {}
    v[9] = _f(vad.get("valence")); v[10] = _f(vad.get("arousal")); v[11] = _f(vad.get("dominance"))
    return v if any(x is not None for x in v) else None


def masked_mean(vecs, weights=None):
    """逐维掩码加权均值;某维全缺则该维 None。"""
    if not vecs:
        return None
    weights = weights or [1.0] * len(vecs)
    out = [None] * DIM
    for d in range(DIM):
        s = w = 0.0
        for vec, wt in zip(vecs, weights):
            if vec[d] is not None and wt > 0:
                s += vec[d] * wt; w += wt
        out[d] = s / w if w else None
    return out


def vec_fill(vec, default=0.5):
    return [default if x is None else x for x in (vec or [])] or [default] * DIM


def dKG(a, b):
    """kg-me 距离:0.5·dWV + 0.3·dLang + 0.2·dAff(各自归一到 0-1)。掩码:任一维缺按 0.5 处理。"""
    a = vec_fill(a); b = vec_fill(b)
    dwv = math.hypot(a[0] - b[0], a[1] - b[1]) / math.sqrt(2)
    dl = math.sqrt(sum((a[2 + i] - b[2 + i]) ** 2 for i in range(7))) / math.sqrt(7)
    daf = math.hypot(a[9] - b[9], a[10] - b[10]) / math.sqrt(2)
    return 0.5 * dwv + 0.3 * dl + 0.2 * daf


def spread_of(vecs, mu):
    """离散度 = 各作品到 μ 的平均 dKG。"""
    if not vecs or mu is None:
        return 0.0
    return sum(dKG(v, mu) for v in vecs) / len(vecs)


def region_of(vec):
    """落在哪个世界观区(按 wv x/y 最近中心)。"""
    vx = vec[0] if vec[0] is not None else 0.5
    vy = vec[1] if vec[1] is not None else 0.5
    best = min(WV_REGIONS, key=lambda r: math.hypot(vx - r[2], vy - r[3]))
    return best[0], best[1]


# ---------------- 艺术家质心 ----------------
def build_artist_vectors(min_works=3):
    """从 works.vlm 聚合每位艺术家的 12 维质心 → mu_artist_vec。"""
    conn = _conn(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""SELECT a.artist_id, a.name_cn, a.name_en, a.region, w.vlm
                   FROM artists a JOIN works w ON w.artist_id=a.artist_id
                   WHERE w.vlm->'affect'->'vad' IS NOT NULL""")
    by = {}
    for r in cur.fetchall():
        v = work_vec(r["vlm"])
        if v is None:
            continue
        by.setdefault(r["artist_id"], {"cn": r["name_cn"], "en": r["name_en"], "region": r["region"], "vecs": []})
        by[r["artist_id"]]["vecs"].append(v)
    cur2 = conn.cursor(); n = 0
    for aid, d in by.items():
        if len(d["vecs"]) < min_works:
            continue
        mu = masked_mean(d["vecs"]); muf = vec_fill(mu)
        cur2.execute("""INSERT INTO mu_artist_vec(artist_id,cn,en,region,n,vec,wv_x,wv_y,updated)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,now())
                        ON CONFLICT(artist_id) DO UPDATE SET cn=EXCLUDED.cn,en=EXCLUDED.en,region=EXCLUDED.region,
                          n=EXCLUDED.n,vec=EXCLUDED.vec,wv_x=EXCLUDED.wv_x,wv_y=EXCLUDED.wv_y,updated=now()""",
                     (aid, d["cn"], d["en"], d["region"], len(d["vecs"]), muf, muf[0], muf[1]))
        n += 1
    conn.commit(); conn.close()
    return n


def _artist_vectors(cur):
    cur.execute("SELECT artist_id,cn,en,region,vec FROM mu_artist_vec")
    return cur.fetchall()


def nearest_artist(mu, cur):
    rows = _artist_vectors(cur)
    if not rows:
        return None
    best = min(rows, key=lambda r: dKG(mu, r["vec"]))
    return {"artist_id": best["artist_id"], "cn": best["cn"] or best["en"],
            "aff": round(max(0.0, 1 - dKG(mu, best["vec"])) * 100)}


# ---------------- 用户档案 ----------------
def _engaged(cur, uid):
    """取用户参与作品:work_id 直连 OR 旧事件靠 files.cos_key=target_id 反查。返回 [(vec,weight,wv,arousal,ts),...] 时间正序。"""
    cur.execute("""
      SELECT e.kind, e.ts, w.vlm
      FROM mu_event e
      JOIN files f ON (e.work_id IS NOT NULL AND f.work_id=e.work_id)
                   OR (e.work_id IS NULL AND f.cos_key=e.target_id)
      JOIN works w ON w.work_id=f.work_id
      WHERE e.uid=%s AND e.kind IN ('open','dwell','like','collect','gen','view','skip')
        AND w.vlm IS NOT NULL
      ORDER BY e.ts ASC""", (uid,))
    out = []
    for r in cur.fetchall():
        v = work_vec(r["vlm"])
        if v is None:
            continue
        out.append((v, EVENT_W.get(r["kind"], 0), r["kind"]))
    return out


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _dim_weights(evecs):
    """学每人维度权重:对 7 个绘画语言维,你越一致(方差越小)=越在意 → 权重越高;归一到均值1。"""
    import statistics
    ws = []
    for i in range(2, 9):
        vals = [v[i] for v in evecs if v[i] is not None]
        sd = statistics.pstdev(vals) if len(vals) >= 3 else 0.25
        ws.append(1.0 / (sd + 0.15))
    m = sum(ws) / len(ws)
    return [x / m for x in ws]


def _dist_w(a, b, wl):
    """个性化距离:沿用 dKG 的 0.5/0.3/0.2 结构,但 7 个语言维按个人权重 wl 加权。"""
    a = vec_fill(a); b = vec_fill(b)
    dwv = math.hypot(a[0] - b[0], a[1] - b[1]) / math.sqrt(2)
    den = sum(wl); num = sum(wl[i] * (a[2 + i] - b[2 + i]) ** 2 for i in range(7))
    dl = math.sqrt(num / den) if den else 0.0
    daf = math.hypot(a[9] - b[9], a[10] - b[10]) / math.sqrt(2)
    return 0.5 * dwv + 0.3 * dl + 0.2 * daf


LAMP_WIN = 50  # 三盏灯滑动窗:最近 ~50 次参与构成"近期看画状态"(相对稳定的终身 μ/d*)

def _lamps(win, mu, dstar):
    """三盏灯 = 近期看画状态(滑动窗 win=最近 N 次参与的 [(vec,weight)…]),相对稳定的终身 μ / 惊奇带 d*。
       —— 用近窗而非全期累计,所以会随近况自然波动;比"一生平均"更贴"看画状态"的语义。"""
    if not win:
        return {"epiphany": 0.0, "growth": 0.0, "calm": 0.0}
    # 顿悟密度:近窗里"强心动(like/collect/gen)"落在你惊奇甜点 d* 附近的程度(倒U,相对稳定 μ)。
    #   旧版阈值是"到 μ 的平均距离"自指→恒为1;改成以 d* 为峰的高斯,既不钉死又随近期心动的新意起伏。
    SIG = 0.18
    likes = [v for v, w in win if w >= 2]
    if likes:
        epiphany = sum(math.exp(-((dKG(v, mu) - dstar) ** 2) / (2 * SIG * SIG)) for v in likes) / len(likes)
    else:
        epiphany = 0.0
    # 审美成长:近窗重心偏离终身 μ 的漂移(在拓展)+ 近窗触及世界观区的熵(在开阔)。探新→升,守旧→落。
    cen = masked_mean([v for v, w in win], [w for v, w in win])
    drift = dKG(cen, mu) if cen else 0.0
    regs = {}
    for v, w in win:
        r, _ = region_of(v); regs[r] = regs.get(r, 0) + 1
    tot = sum(regs.values()); H = 0.0
    if tot:
        for c in regs.values():
            p = c / tot
            if p > 0:
                H -= p * math.log(p)
    Hn = H / math.log(len(regs)) if len(regs) > 1 else 0.0
    growth = _clamp(0.55 * Hn + 0.45 * _clamp(drift / 0.22))
    # 安静感:近窗唤起的低唤醒程度(设定点 0.34)+ 平顺(相邻抖动小)。近期看得越燥→越低。
    ar = [v[10] for v, w in win if v[10] is not None]
    if ar:
        m = sum(ar) / len(ar)
        j = sum(abs(ar[i] - ar[i - 1]) for i in range(1, len(ar))) / (len(ar) - 1) if len(ar) > 1 else 0.0
        calm = _clamp(1 - 0.8 * abs(m - 0.34) - 0.6 * j)
    else:
        calm = 1.0
    return {"epiphany": round(epiphany, 3), "growth": round(growth, 3), "calm": round(calm, 3)}


def compute_profile(uid, persist=True):
    """算 uid 的 12 维档案(μ/spread/门派/本命/三盏灯/d*)并 upsert mu_profile。返回 dict。"""
    conn = _conn(); cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        eng = _engaged(cur, uid)
        pos = [(v, w) for (v, w, k) in eng if w > 0]
        if not pos:
            return {"uid": uid, "ready": False, "n": 0}
        vecs = [v for v, w in pos]; ws = [w for v, w in pos]
        mu = masked_mean(vecs, ws)
        # 对比学习:被拒(skip)作品作为排斥项,把 μ 往"远离被略过的那类"方向推一点。
        # 二选一序幕里"没选的"也是信号——每轮的取舍把 μ 沿偏好方向拉得更准。
        # 仅在累计 ≥2 个 skip 时启用(避免单点噪声);逐维有界推动,clamp 回 [0,1] 不外溢。
        neg_vecs = [v for (v, w, k) in eng if k == 'skip']
        n_neg = len(neg_vecs)
        if n_neg >= 2:
            mu_neg = masked_mean(neg_vecs)
            if mu_neg:
                ALPHA = 0.35  # 排斥强度;0.35≈选中权重(like=3)的一档,稳健不过冲
                mu = [_clamp(mu[d] + ALPHA * (mu[d] - mu_neg[d]))
                      if (mu[d] is not None and mu_neg[d] is not None) else mu[d]
                      for d in range(DIM)]
        sess_vecs = [v for v, w in pos[-20:]]; sess = masked_mean(sess_vecs)
        sp = spread_of(vecs, mu)
        # 漂移:近况 μ 与全期 μ 的距离(settled 判据)
        drift = dKG(sess, mu)
        # d* 自学习:从接受的作品到 μ 的距离均值估个人惊奇带(简化稳健版)
        ds_samples = [dKG(v, mu) for v, w in pos if w >= 2]
        dstar = _clamp(sum(ds_samples) / len(ds_samples) if ds_samples else 0.30, 0.15, 0.6)
        explore = 0.30
        # 门派 = 区(6) × 亚型(8)
        rid, rname = region_of(mu)
        focus = sp < 0.13; settled = drift < 0.05; cautious = dstar < 0.36
        sub = SUBTYPE[('1' if focus else '0') + ('1' if settled else '0') + ('1' if cautious else '0')]
        archetype = f"{rname}·{sub}"
        # 本命画家
        soul = nearest_artist(mu, cur)
        # 三盏灯 = 近期「看画状态」:用最近 LAMP_WIN 次参与的滑动窗,相对稳定的终身 μ / d* 来算 → 随近况自然波动
        muf = vec_fill(mu)
        lights = _lamps(pos[-LAMP_WIN:], mu, dstar)
        # 成熟度/置信:12 维 μ 至少要 ~20+ 个正反馈才稳;诚实告诉用户档案有多可信,别把冷启动当定论。
        npos = len(pos)
        maturity = round(_clamp(npos / 22.0), 2)
        mat_level = "清晰" if npos >= 20 else ("成形中" if npos >= 8 else "初识")
        prof = {
            "uid": uid, "ready": True, "n": npos, "n_neg": n_neg,
            "vec": [round(x, 3) for x in muf], "vec_sess": [round(x, 3) for x in vec_fill(sess)],
            "spread": round(sp, 3), "drift": round(drift, 3),
            "archetype": archetype, "arche_region": rid, "arche_region_name": rname,
            "arche_sub": sub, "arche_sub_desc": SUBDESC[sub],
            "soulmate": soul, "lights": lights, "dstar": round(dstar, 3), "explore": explore,
            "maturity": maturity, "maturity_level": mat_level, "need_more": max(0, 8 - npos),
        }
        if persist:
            cur.execute("""INSERT INTO mu_profile(uid,vec,vec_sess,spread,n,archetype,arche_region,arche_sub,
                             soulmate,soulmate_cn,soulmate_aff,lights,dstar,explore,updated)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                           ON CONFLICT(uid) DO UPDATE SET vec=EXCLUDED.vec,vec_sess=EXCLUDED.vec_sess,
                             spread=EXCLUDED.spread,n=EXCLUDED.n,archetype=EXCLUDED.archetype,
                             arche_region=EXCLUDED.arche_region,arche_sub=EXCLUDED.arche_sub,
                             soulmate=EXCLUDED.soulmate,soulmate_cn=EXCLUDED.soulmate_cn,soulmate_aff=EXCLUDED.soulmate_aff,
                             lights=EXCLUDED.lights,dstar=EXCLUDED.dstar,explore=EXCLUDED.explore,updated=now()""",
                        (uid, muf, vec_fill(sess), sp, len(pos), archetype, rid, sub,
                         soul["artist_id"] if soul else None, soul["cn"] if soul else None,
                         soul["aff"] if soul else None, json.dumps(lights), dstar, explore))
            # 成长时间序列:n 变化≥2 才追加一条快照(供「审美成长曲线」)
            cur.execute("CREATE TABLE IF NOT EXISTS mu_history(id serial PRIMARY KEY, uid text, ts timestamptz DEFAULT now(), n int, vec jsonb, spread real, lights jsonb)")
            cur.execute("SELECT n FROM mu_history WHERE uid=%s ORDER BY ts DESC LIMIT 1", (uid,))
            _last = cur.fetchone()
            if _last is None or abs((_last["n"] or 0) - len(pos)) >= 2:
                cur.execute("INSERT INTO mu_history(uid,n,vec,spread,lights) VALUES(%s,%s,%s,%s,%s)",
                            (uid, len(pos), json.dumps([round(x, 3) for x in muf]), round(sp, 3), json.dumps(lights)))
            conn.commit()
        return prof
    finally:
        conn.close()


def resolve_token(tok):
    """把收藏/历史里任意形态的 token 归一成『可解析的图源描述』。统一图片解析的唯一入口。
       token 历史上是个杂物箱:数字 work_id / 'img/..' / '/img/..'(前导斜杠) / http URL / 含中文的 cos_key。
       返回 (kind, key):kind ∈ {'id','img','http','cos'};key=用于解析/反查的规范键。"""
    t = (tok or "").strip()
    if not t:
        return (None, None)
    if t.startswith("http://") or t.startswith("https://"):
        return ("http", t)
    if t.startswith("/"):
        t = t.lstrip("/")            # 归一前导斜杠:'/img/..' → 'img/..'
    if t.startswith("img/"):
        return ("img", t)
    if t.isdigit():
        return ("id", t)
    if "/" in t:                     # 形如 artworks/油画数据集/.. 的 cos_key(可能含非 ASCII)
        return ("cos", t)
    return ("id", t)                 # 兜底当作 work_id


def collections_view(uid, thumb=480):
    """把 uid 的收藏解析成结构化、URL 已正确编码、可点的卡片列表(供 me.html 收藏墙)。
       统一走 img_url(自动百分号编码 + 缩略),数字 id/文件 key 都反查 works/artists 补标题作者。
       不在这里物理删任何收藏;解析不出图的条目带 broken 标记,前端兜底占位,绝不渲染裂图。"""
    conn = _conn(); cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT work_id, ts FROM mu_collection WHERE uid=%s ORDER BY ts DESC", (uid,))
        rows = cur.fetchall()
        ids, keys = set(), set()
        parsed = []
        for r in rows:
            kind, key = resolve_token(r["work_id"])
            parsed.append((r["work_id"], kind, key))
            if kind == "id":
                ids.add(key)
            elif kind in ("img", "cos"):
                keys.add(key)
        meta_by_id, meta_by_key = {}, {}
        if ids:
            cur.execute("""SELECT w.work_id, w.title, a.name_cn, a.name_en, f.cos_key
                           FROM works w JOIN files f ON f.work_id=w.work_id
                           LEFT JOIN artists a ON a.artist_id=w.artist_id
                           WHERE w.work_id = ANY(%s)""", ([int(x) for x in ids],))
            for m in cur.fetchall():
                meta_by_id[str(m["work_id"])] = m
        if keys:
            cur.execute("""SELECT f.cos_key, w.work_id, w.title, a.name_cn, a.name_en
                           FROM files f JOIN works w ON w.work_id=f.work_id
                           LEFT JOIN artists a ON a.artist_id=w.artist_id
                           WHERE f.cos_key = ANY(%s)""", (list(keys),))
            for m in cur.fetchall():
                meta_by_key[m["cos_key"]] = m
        items = []
        for raw, kind, key in parsed:
            title = artist = wid = None
            if kind == "http":
                full = key
                thb = key + ("?imageMogr2/thumbnail/%dx" % thumb if ("myqcloud.com" in key and "?" not in key) else "")
            elif kind == "id":
                m = meta_by_id.get(key)
                if not m or not m["cos_key"]:
                    items.append({"raw": raw, "broken": True}); continue
                full = img_url(m["cos_key"]); thb = img_url(m["cos_key"], thumb)
                title = m["title"]; artist = m["name_cn"] or m["name_en"]; wid = m["work_id"]
            else:  # img / cos
                full = img_url(key); thb = img_url(key, thumb if kind == "cos" else None)
                m = meta_by_key.get(key)
                if m:
                    title = m["title"]; artist = m["name_cn"] or m["name_en"]; wid = m["work_id"]
            items.append({"raw": raw, "work_id": wid, "title": title, "artist": artist,
                          "thumb": thb, "full": full, "broken": False})
        return items
    finally:
        conn.close()


def journey(uid):
    """审美成长时间序列:历次重心快照(供前端画轨迹/成长曲线)。"""
    conn = _conn(); cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("CREATE TABLE IF NOT EXISTS mu_history(id serial PRIMARY KEY, uid text, ts timestamptz DEFAULT now(), n int, vec jsonb, spread real, lights jsonb)")
        cur.execute("SELECT ts,n,vec,spread,lights FROM mu_history WHERE uid=%s ORDER BY ts ASC LIMIT 300", (uid,))
        return [{"ts": str(r["ts"]), "n": r["n"], "vec": r["vec"], "spread": r["spread"], "lights": r["lights"]} for r in cur.fetchall()]
    finally:
        conn.close()


def lamp_trace(uid, points=140):
    """三盏灯的"心跳图"密集序列:回放参与事件,沿时间在 ~points 个等距位置滑动 LAMP_WIN 窗算三盏灯。
       —— mu_history 只有稀疏快照,这里直接从事件重算出细颗粒度曲线,让波动像心跳一样直观。"""
    conn = _conn(); cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        eng = _engaged(cur, uid)
        pos = [(v, w) for (v, w, k) in eng if w > 0]
        N = len(pos)
        if N < 4:
            return []
        mu = masked_mean([v for v, w in pos], [w for v, w in pos])
        ds = [dKG(v, mu) for v, w in pos if w >= 2]
        dstar = _clamp(sum(ds) / len(ds) if ds else 0.30, 0.15, 0.6)
        lo = min(max(4, LAMP_WIN // 2), N)            # 起点:窗里有点数据再开始
        pts = max(2, min(points, N - lo + 1))
        idxs = sorted(set(int(round(lo + (N - lo) * t / (pts - 1))) for t in range(pts)))
        out = []
        for i in idxs:
            L = _lamps(pos[max(0, i - LAMP_WIN):i], mu, dstar)
            out.append({"epiphany": L["epiphany"], "growth": L["growth"], "calm": L["calm"], "n": i})
        return out
    finally:
        conn.close()


# ---------------- 语音/文字 wish 的『近来意图』偏置 ----------------
def wish_signal(cur, uid, halflife_days=7.0, window_days=45):
    """把近 window_days 的 wish 聚成一个按 halflife 衰减加权的目标偏置(陈述偏好/stated)。
       只在被提到的维度给目标值:region→世界观(idx0,1)、av→唤起(idx10)、vv→愉悦(idx9)。
       返回 (target{dim:val}, conf, recent_text)。conf=累计权重封顶,用来限制对推荐的拉动幅度。
       —— 此刻心情(30 分钟)归 next_frame;近来意图(7 天半衰期)归这里;都不写进长期 μ(身份)。"""
    cur.execute("""SELECT text, av, vv, region,
                          exp(-ln(2)*extract(epoch from now()-ts)/86400.0/%s) AS wgt
                   FROM mu_wish WHERE uid=%s AND ts > now()-(%s||' days')::interval
                     AND (av IS NOT NULL OR vv IS NOT NULL OR region IS NOT NULL)
                   ORDER BY ts DESC LIMIT 50""", (halflife_days, uid, window_days))
    rows = cur.fetchall()
    if not rows:
        return ({}, 0.0, None)
    REGC = {r[0]: (r[2], r[3]) for r in WV_REGIONS}   # 区 id → 世界观中心 (x,y)
    acc = {}
    def add(dim, val, wt):
        a = acc.setdefault(dim, [0.0, 0.0]); a[0] += wt * val; a[1] += wt
    tot_w = 0.0
    for r in rows:
        wt = float(r["wgt"] or 0.0); tot_w += wt
        if r["av"] is not None: add(10, float(r["av"]), wt)
        if r["vv"] is not None: add(9, float(r["vv"]), wt)
        if r["region"] and r["region"] in REGC:
            add(0, REGC[r["region"]][0], wt); add(1, REGC[r["region"]][1], wt)
    target = {d: a[0] / a[1] for d, a in acc.items() if a[1] > 0}
    conf = min(1.0, tot_w / 2.0)                       # 累计权重≈2(约两条近期 wish)即满置信
    return (target, conf, rows[0]["text"])


# ---------------- 为你推荐(reward 内核) ----------------
def foryou(uid, limit=24, pool=600, w=None, log_impr=False, algo=None):
    """reward = aha顿悟(倒U)·calm·info·growth − 厌恶惩罚;在 kept+可向量化作品里排序。
       叠加『近来 wish 意图』:把锚点 μ 朝 wish 目标推 GAMMA·conf(只动被提到的维度),不改长期 μ。
       algo='knn':多峰召回——不用单一重心,而是到你 k 个最近喜欢作品的加权距离(学每人维度权重),
                  对『多峰口味』(既爱宋画又爱表现主义)更准;<3 个正样本自动回退重心。默认 None=原重心法。
       log_impr=True 时记录曝光到 mu_rec_log(strat 区分 prod/knn),供 rec_lift() A/B 评估。"""
    conn = _conn(); cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT vec,spread,dstar,n FROM mu_profile WHERE uid=%s", (uid,))
        p = cur.fetchone()
        if not p or not p["vec"]:
            prof = compute_profile(uid)
            if not prof.get("ready"):
                return {"ready": False, "items": []}
            mu = prof["vec"]; dstar = prof["dstar"]; pn = prof["n"]
        else:
            mu = p["vec"]; dstar = p["dstar"]; pn = p.get("n") or 0
        # 近来 wish 偏置:μ → μ_eff(被提到的维度朝目标推一点,conf 限幅;身份 μ 不动)
        wt_target, wt_conf, wt_text = wish_signal(cur, uid)
        mu_eff = list(mu)
        if wt_conf > 0 and wt_target:
            GAMMA = 0.6
            for d, tv in wt_target.items():
                if d < len(mu_eff) and mu_eff[d] is not None:
                    mu_eff[d] = _clamp(mu_eff[d] + GAMMA * wt_conf * (tv - mu_eff[d]))
        mu = mu_eff
        # 多峰召回准备:取正样本向量 + 学每人维度权重(<3 个正样本则回退重心法)
        knn = (algo == "knn"); evecs = []; wl = [1.0] * 7
        if knn:
            evecs = [v for (v, wt, _k) in _engaged(cur, uid) if wt > 0][-60:]
            if len(evecs) < 3: knn = False
            else: wl = _dim_weights(evecs)
        # 已看过的作品(避免重复推荐)
        cur.execute("""SELECT DISTINCT f.work_id FROM mu_event e JOIN files f
                       ON (e.work_id IS NOT NULL AND f.work_id=e.work_id) OR (e.work_id IS NULL AND f.cos_key=e.target_id)
                       WHERE e.uid=%s""", (uid,))
        seen = {r["work_id"] for r in cur.fetchall()}
        # 候选:已策展或高质量 + 有向量
        cur.execute("""SELECT w.work_id, w.title, a.name_cn, a.name_en, f.cos_key, w.vlm,
                              w.quality qc
                       FROM works w JOIN files f ON f.work_id=w.work_id
                       LEFT JOIN artists a ON a.artist_id=w.artist_id
                       WHERE w.status='kept' AND w.vlm->'affect'->'vad' IS NOT NULL
                       ORDER BY w.exhibited DESC NULLS LAST, w.quality DESC NULLS LAST
                       LIMIT %s""", (pool,))
        sigma = 0.20
        W = w or {}
        # 探索度 ex = 「熟悉↔惊喜」滑块(沿用 aha 键)。默认随成熟度:冷启动偏熟悉(相似),成熟才偏惊喜(倒U)。
        # 这修了结构性缺陷——旧版只有倒U、没有相似度项,对「口味一致」型用户失效(评估实证)。
        maturity = _clamp(pn / 22.0)
        ex = float(W['aha']) if ('aha' in W) else _clamp(0.25 + 0.45 * maturity, 0.2, 0.7)
        wc = float(W.get('calm', 0.15)); wq = float(W.get('qual', 0.30))
        scored = []
        for r in cur.fetchall():
            if r["work_id"] in seen:
                continue
            v = work_vec(r["vlm"])
            if v is None:
                continue
            if knn:                                                # 多峰:到 k 个最近喜欢作品的加权距离(非重心)
                ds = sorted(_dist_w(v, e, wl) for e in evecs)[:3]
                d = sum(ds) / len(ds)
            else:
                d = dKG(v, mu)
            sim = 1 - d                                            # 熟悉:越靠近你的口味越高
            aha = math.exp(-((d - dstar) ** 2) / (2 * sigma * sigma))  # 惊喜:落在惊奇带 d*
            ar = v[10] if v[10] is not None else 0.5
            calm = _clamp(1 - abs(ar - 0.34))
            qc = float(r["qc"]) if r["qc"] is not None else 0.5
            rel = (1 - ex) * sim + ex * aha                        # 相关度 = 熟悉↔惊喜 混合
            tot = rel + wc * calm + wq * qc
            scored.append((tot, d, r))
        scored.sort(key=lambda t: -t[0])
        items = []
        for rank, (tot, d, r) in enumerate(scored[:limit], 1):
            items.append({"work_id": r["work_id"], "title": r["title"],
                          "artist": r["name_cn"] or r["name_en"], "cos_key": r["cos_key"],
                          "thumb": img_url(r["cos_key"], 360), "img": img_url(r["cos_key"]),
                          "score": round(tot, 3), "dist": round(d, 3), "rank": rank})
        if log_impr and items:
            _log_impressions(cur, conn, uid, items, strat=("knn" if knn else "prod"))   # 在线埋点(best-effort)
        wish_out = {"text": wt_text, "conf": round(wt_conf, 2)} if (wt_conf > 0 and wt_text) else None
        return {"ready": True, "items": items, "wish": wish_out, "algo": ("knn" if knn else "centroid")}
    finally:
        conn.close()


def _log_impressions(cur, conn, uid, items, strat="prod"):
    """记录一次推荐曝光(uid×work×名次×分数),日后和真实行为 join 算 lift。失败不影响推荐。"""
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS mu_rec_log(
            id serial PRIMARY KEY, uid text, work_id bigint, strat text,
            rank int, score real, dist real, ts timestamptz DEFAULT now())""")
        cur.execute("CREATE INDEX IF NOT EXISTS mu_rec_log_uid_ts ON mu_rec_log(uid, ts)")
        args = [(uid, it["work_id"], strat, it["rank"], it["score"], it["dist"])
                for it in items if it.get("work_id") is not None]
        cur.executemany("""INSERT INTO mu_rec_log(uid,work_id,strat,rank,score,dist)
                           VALUES(%s,%s,%s,%s,%s,%s)""", args)
        conn.commit()
    except Exception:
        conn.rollback()


def rec_lift(days=14, window_hours=72):
    """在线评估:被推荐过的作品,在曝光后 window 内被该用户 like/collect/dwell 的比例,
       对照同用户对‘没推过’作品的基础参与率。lift>1 = 推荐确实提升了参与(离线代理看不见的真信号)。"""
    conn = _conn(); cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT to_regclass('mu_rec_log') IS NOT NULL ok")
        if not cur.fetchone()["ok"]:
            return {"ready": False, "msg": "还没有推荐曝光日志(mu_rec_log)"}
        # 推荐命中:曝光后 window_hours 内对同一 work 有正反馈
        cur.execute("""
          SELECT count(DISTINCT (l.uid,l.work_id)) impressions,
                 count(DISTINCT (l.uid,l.work_id)) FILTER (WHERE e.work_id IS NOT NULL) hits
          FROM mu_rec_log l
          LEFT JOIN mu_event e
            ON e.uid=l.uid AND e.work_id=l.work_id AND e.kind IN ('like','collect','dwell')
               AND e.ts BETWEEN l.ts AND l.ts + (%s||' hours')::interval
          WHERE l.ts > now() - (%s||' days')::interval""", (window_hours, days))
        r = cur.fetchone(); imp = r["impressions"] or 0; hits = r["hits"] or 0
        # 基础率:这些用户整体正反馈 / 看过的不同作品
        cur.execute("""SELECT count(*) FILTER (WHERE kind IN ('like','collect','dwell'))::float
                              / NULLIF(count(DISTINCT work_id),0) base
                       FROM mu_event WHERE uid IN (SELECT DISTINCT uid FROM mu_rec_log)
                         AND work_id IS NOT NULL""")
        base = cur.fetchone()["base"] or 0
        ctr = hits / imp if imp else 0
        return {"ready": True, "impressions": imp, "hits": hits,
                "rec_ctr": round(ctr, 3), "base_rate": round(base, 3),
                "lift": round(ctr / base, 2) if base else None,
                "note": "lift>1 = 推荐比该用户平均更易被参与;需积累曝光后才有意义"}
    finally:
        conn.close()


def _wish_keywords(t):
    """关键词兜底解析(LLM 不可用时):盲于否定,仅作 fallback。返回 (av, vv, region)。"""
    av = vv = None; region = None
    LO_AR = ['安静', '宁静', '平静', '柔和', '静谧', '清冷', '素净', '淡雅', '舒缓', '治愈']
    HI_AR = ['热烈', '激烈', '强烈', '震撼', '有力', '奔放', '张扬', '浓烈', '澎湃', '燃']
    HI_VV = ['明亮', '欢快', '温暖', '愉悦', '喜庆', '灿烂', '阳光', '希望', '甜', '轻快']
    LO_VV = ['忧郁', '悲伤', '孤独', '沉郁', '苍凉', '压抑', '哀', '寂', '冷清', '萧瑟']
    REGS = [('WV3', ['山水', '写意', '水墨', '文人', '意境', '留白', '禅']),
            ('WV4', ['印象', '外光', '光影', '色彩', '斑斓', '瞬间', '莫奈']),
            ('WV6', ['抽象', '几何', '构成', '形式', '立体', '极简']),
            ('WV1', ['写实', '肖像', '古典', '逼真', '学院', '细腻']),
            ('WV5', ['表现', '梵高', '呐喊', '情绪', '笔触', '狂野']),
            ('WV2', ['装饰', '宗教', '秩序', '庄重', '图案', '神圣'])]
    if any(w in t for w in LO_AR): av = 0.2
    elif any(w in t for w in HI_AR): av = 0.8
    if any(w in t for w in HI_VV): vv = 0.78
    elif any(w in t for w in LO_VV): vv = 0.25
    for rid, kw in REGS:
        if any(k in t for k in kw):
            region = rid; break
    return av, vv, region


WISH_SYS = """你是 aha 的「心愿解析器」。用户用一句话说出此刻想看什么样的画,把它映射到三个推荐变量:
① region 门派(取其一或 null):
   WV1 摹写之眼=写实/肖像/古典/逼真/学院;WV2 礼制图式=装饰/宗教/秩序/庄重/图案;
   WV3 写意寄情=山水/水墨/文人/意境/留白/禅;WV4 经验之光=印象/外光/光影/斑斓色彩/瞬间;
   WV5 表现外化=表现主义/梵高/强烈情绪/狂野笔触;WV6 形式建构=抽象/几何/构成/极简。
② valence 愉悦 0-1(0=忧郁低沉,1=明亮欢快)或 null。
③ arousal 唤起 0-1(0=安静平和,1=激烈有力)或 null。
铁律:**必须正确处理否定与程度**——「不要太安静」=想要高唤起(arousal≈0.7);「别那么沉重」=高愉悦;
「淡一点」「柔和些」=低唤起。没把握的维度给 null,绝不硬猜。
只输出 JSON,无多余文字:{"region":"WV3"|null,"valence":0.0-1.0|null,"arousal":0.0-1.0|null,"reason":"一句话依据"}"""


def _mimo_json(system, user, max_tokens=4000, timeout=40):
    """调小米 MiMo(Anthropic 兼容 /v1/messages)做一次文本→JSON。失败返回 None。推理模型需大 max_tokens。"""
    import urllib.request
    try:
        cfg = json.load(open(os.path.expanduser('~/.aha_mimo.json')))
    except Exception:
        return None
    body = {"model": cfg['model'], "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": user}]}
    req = urllib.request.Request(cfg['endpoint'].rstrip('/') + '/v1/messages',
                                 data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", "x-api-key": cfg['key'],
                                          "anthropic-version": "2023-06-01"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
        txt = ''.join(b.get('text', '') for b in d.get('content', []) if b.get('type') == 'text')
    except Exception:
        return None
    i = txt.find('{')
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(txt)):           # 简单括号配平抽 JSON
        if txt[j] == '{': depth += 1
        elif txt[j] == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(txt[i:j + 1])
                except Exception:
                    return None
    return None


def parse_wish_llm(t):
    """LLM 解析心愿 → (av, vv, region, parsed)。能处理否定/程度/细微。失败返回全 None。"""
    o = _mimo_json(WISH_SYS, "用户说:" + t)
    if not isinstance(o, dict):
        return None, None, None, None
    def num(x):
        try:
            x = float(x); return x if 0.0 <= x <= 1.0 else None
        except Exception:
            return None
    reg = o.get("region")
    if reg not in ("WV1", "WV2", "WV3", "WV4", "WV5", "WV6"):
        reg = None
    return num(o.get("arousal")), num(o.get("valence")), reg, o


def record_wish(uid, text):
    """把相框里长按说出的"想法/心情"解析成一个临时推荐偏置(情绪+门派),入库 mu_wish。
       优先用 LLM(能处理否定/程度),失败回退关键词。近 30 分钟内 next_frame 会朝它倾斜。"""
    t = (text or "").strip()[:120]
    parsed = None; src = "kw"
    av, vv, region, parsed = parse_wish_llm(t) if t else (None, None, None, None)
    if av is None and vv is None and region is None:     # LLM 没拿到→关键词兜底
        av, vv, region = _wish_keywords(t)
    else:
        src = "llm"
    conn = _conn(); cur = conn.cursor()
    try:
        cur.execute("CREATE TABLE IF NOT EXISTS mu_wish(id serial PRIMARY KEY, uid text, ts timestamptz DEFAULT now(), text text, av real, vv real, region text)")
        cur.execute("ALTER TABLE mu_wish ADD COLUMN IF NOT EXISTS parsed jsonb")
        cur.execute("ALTER TABLE mu_wish ADD COLUMN IF NOT EXISTS src text")
        cur.execute("INSERT INTO mu_wish(uid,text,av,vv,region,parsed,src) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (uid, t, av, vv, region, json.dumps(parsed, ensure_ascii=False) if parsed else None, src))
        conn.commit()
    finally:
        conn.close()
    return {"text": t, "av": av, "vv": vv, "region": region, "src": src,
            "reason": (parsed or {}).get("reason"),
            "hit": (av is not None or vv is not None or region is not None)}


# ---------------- 智能相框 / 电台(被动展示 + 衰减召回) ----------------
def next_frame(uid, n=8, pool=1600, ch=None, tod=None, seen=None):
    """相框轮播:按 契合(惊奇带) × 衰减(反复曝光未互动) × 探索 + 随机 采样下一批。
       ch=频道(calm/masters/explore/surprise/home);tod=小时(夜间偏安静)。
       seen=本场已看过的 work_id(逗号串或列表),从候选里直接剔除,杜绝同一会话内重播。
       双击收藏=强正(像电台老歌偶尔回放);反复放却没双击→衰减淡出;探索保底防永久封禁。"""
    import random
    conn = _conn(); cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT vec,dstar,n FROM mu_profile WHERE uid=%s", (uid,))
        p = cur.fetchone()
        mu = p["vec"] if (p and p["vec"]) else None
        dstar = (p["dstar"] if (p and p.get("dstar")) else 0.34)
        # 默认台「顺心」的熟悉↔惊喜随成熟度:冷启动偏熟悉(相似),成熟才偏惊喜(倒U)。与 foryou 一致,补相似度项。
        ex = _clamp(0.25 + 0.45 * _clamp(((p["n"] if p else 0) or 0) / 22.0), 0.2, 0.7)
        cur.execute("""SELECT target_id k,
                          count(*) FILTER (WHERE kind IN ('like','collect','double')) lk,
                          count(*) FILTER (WHERE kind='dislike') dis,
                          COALESCE(sum(CASE WHEN kind='expose' THEN exp(-extract(epoch from now()-ts)/259200.0) ELSE 0 END),0) strike,
                          extract(epoch from now()-max(ts)) age_s
                        FROM mu_event WHERE uid=%s AND target_id IS NOT NULL GROUP BY target_id""", (uid,))
        sig = {r["k"]: r for r in cur.fetchall()}
        # 心愿偏置:近 30 分钟内长按说出的想法(情绪/门派),朝它倾斜
        wav = wvv = wreg = None
        cur.execute("CREATE TABLE IF NOT EXISTS mu_wish(id serial PRIMARY KEY, uid text, ts timestamptz DEFAULT now(), text text, av real, vv real, region text)")
        cur.execute("SELECT av,vv,region FROM mu_wish WHERE uid=%s AND ts > now()-interval '30 minutes' ORDER BY ts DESC LIMIT 1", (uid,))
        _wi = cur.fetchone()
        if _wi:
            wav = _wi["av"]; wvv = _wi["vv"]; wreg = _wi["region"]
        seen_ids = []
        for s in (seen.split(',') if isinstance(seen, str) else (seen or [])):
            try:
                seen_ids.append(int(s))
            except Exception:
                pass
        cur.execute("""SELECT w.work_id, w.title, a.name_cn, a.name_en, f.cos_key, w.vlm, w.quality qc
                       FROM works w JOIN files f ON f.work_id=w.work_id
                       LEFT JOIN artists a ON a.artist_id=w.artist_id
                       WHERE w.status='kept' AND w.vlm->'affect'->'vad' IS NOT NULL
                         AND (%(seen)s::bigint[] IS NULL OR w.work_id <> ALL(%(seen)s::bigint[]))
                       ORDER BY w.quality DESC NULLS LAST LIMIT %(pool)s""",
                    {'seen': (seen_ids or None), 'pool': pool})
        sigma = 0.22
        try:
            hour = int(tod) if tod is not None else None
        except Exception:
            hour = None
        night = (hour is not None) and (hour >= 22 or hour < 7)
        user_rid = region_of(mu)[0] if (mu is not None and ch == 'home') else None
        scored = []
        for r in cur.fetchall():
            key = r["cos_key"]
            v = work_vec(r["vlm"])
            if v is None:
                continue
            qc = float(r["qc"]) if r["qc"] is not None else 0.5
            ar = v[10] if (len(v) > 10 and v[10] is not None) else 0.5
            d = dKG(v, mu) if mu is not None else None
            if mu is not None:
                aha = math.exp(-((d - dstar) ** 2) / (2 * sigma * sigma))
                fit = (1 - ex) * (1 - d) + ex * aha          # 熟悉↔惊喜混合(默认台用,显式台下方覆盖)
            else:
                fit = 0.5
            base = 0.7 * fit + 0.3 * qc
            # 频道电台:换台=换权重/过滤
            if ch == 'calm':
                base = 0.5 * base + 0.5 * _clamp(1 - abs(ar - 0.28))      # 安静台:偏低唤醒
            elif ch == 'masters':
                base = 0.35 * base + 0.65 * qc                            # 名作台:偏高品质
            elif ch == 'explore' and d is not None:
                base = 0.45 * base + 0.55 * _clamp(d)                     # 探索台:偏远离μ
            elif ch == 'surprise' and d is not None:
                base = math.exp(-((d - dstar) ** 2) / (2 * 0.12 * 0.12))  # 惊喜台:死磕惊奇带
            elif ch == 'home' and user_rid is not None:
                if region_of(v)[0] != user_rid:
                    continue                                              # 同派台:只放你门派
            # 时段自适应:夜间偏安静(低唤醒)
            if night:
                base *= (0.7 + 0.6 * _clamp(1 - ar))
            # 心愿偏置:朝你长按说出的情绪/门派倾斜
            if wav is not None:
                base *= (0.55 + 0.9 * _clamp(1 - abs(ar - wav)))
            if wvv is not None:
                vl = v[9] if (len(v) > 9 and v[9] is not None) else 0.5
                base *= (0.55 + 0.9 * _clamp(1 - abs(vl - wvv)))
            if wreg is not None:
                base *= 1.9 if region_of(v)[0] == wreg else 0.55
            s = sig.get(key)
            lk = (s["lk"] if s else 0) or 0
            dis = (s["dis"] if s else 0) or 0
            strike = float(s["strike"]) if (s and s["strike"]) else 0.0
            age = float(s["age_s"]) if (s and s["age_s"] is not None) else None
            if dis > 0:
                w_ = base * (0.25 ** dis)              # 明确不喜欢:强压(比沉默重得多)
            elif lk > 0:
                w_ = base * 2.2                         # 收藏过:像电台老歌偶尔回放
            else:
                w_ = base * (0.82 ** strike)            # 沉默:strike 随时间自愈(τ=3天),淡出的画会慢慢复活
            if age is not None:
                if age < 150:
                    w_ *= 0.12                          # 刚放过,别立刻重复
                if lk > 0 and age < 86400:
                    w_ *= 0.45                          # 老收藏 1 天内不连放,过后满血召回
            w_ += 0.05
            w_ *= 0.55 + 0.9 * random.random()
            vad = [round((v[9] if (len(v) > 9 and v[9] is not None) else .5), 2), round(ar, 2)]
            scored.append((w_, key, r, vad))
        scored.sort(key=lambda t: -t[0])
        items = []
        used_works = set()
        for w_, key, r, vad in scored:
            if len(items) >= n:
                break
            if r["work_id"] in used_works:        # 同一幅画多文件:只出一次
                continue
            used_works.add(r["work_id"])
            items.append({"work_id": r["work_id"], "title": r["title"],
                          "artist": r["name_cn"] or r["name_en"], "cos_key": key,
                          "img": img_url(key), "thumb": img_url(key, 720), "hi": img_url(key, 1600), "vad": vad})
        return {"items": items, "has_profile": mu is not None}
    finally:
        conn.close()


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--artists" in a:
        print("artist vectors built:", build_artist_vectors())
    elif "--uid" in a:
        print(json.dumps(compute_profile(a[a.index("--uid") + 1]), ensure_ascii=False, indent=2))
    elif "--foryou" in a:
        print(json.dumps(foryou(a[a.index("--foryou") + 1]), ensure_ascii=False, indent=2))
    elif "--all" in a:
        conn = _conn(); cur = conn.cursor()
        cur.execute("SELECT DISTINCT uid FROM mu_event WHERE uid IS NOT NULL")
        uids = [r[0] for r in cur.fetchall()]; conn.close()
        ok = 0
        for u in uids:
            try:
                if compute_profile(u).get("ready"):
                    ok += 1
            except Exception as e:
                print("ERR", u, e)
        print(f"profiles computed: {ok}/{len(uids)}")
    else:
        print(__doc__)
