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
        # 三盏灯
        muf = vec_fill(mu)
        # 顿悟密度:接受里"惊奇带内"占比
        ep = sum(1 for v, w in pos if w >= 2 and dKG(v, mu) > dstar - 0.20)
        intc = sum(1 for v, w in pos if w >= 2)
        epiphany = _clamp(ep / intc) if intc else 0.0
        # 审美成长:访问区熵(开阔)+ 确定度(1-spread 归一)
        regs = {}
        for v, w in pos:
            r, _ = region_of(v); regs[r] = regs.get(r, 0) + 1
        tot = sum(regs.values()); H = 0.0
        if tot:
            for c in regs.values():
                p = c / tot
                if p > 0:
                    H -= p * math.log(p)
        Hn = H / math.log(len(regs)) if len(regs) > 1 else 0.0
        growth = _clamp(0.6 * Hn + 0.4 * (1 - _clamp(sp / 0.4)))
        # 安静感:低唤醒(设定点 0.34)+ 平顺
        ar = [v[10] for v, w in pos if v[10] is not None]
        if ar:
            m = sum(ar) / len(ar)
            j = sum(abs(ar[i] - ar[i - 1]) for i in range(1, len(ar))) / (len(ar) - 1) if len(ar) > 1 else 0
            calm = _clamp(1 - 0.7 * abs(m - 0.34) - 0.8 * j)
        else:
            calm = 1.0
        lights = {"epiphany": round(epiphany, 3), "growth": round(growth, 3), "calm": round(calm, 3)}
        prof = {
            "uid": uid, "ready": True, "n": len(pos), "n_neg": n_neg,
            "vec": [round(x, 3) for x in muf], "vec_sess": [round(x, 3) for x in vec_fill(sess)],
            "spread": round(sp, 3), "drift": round(drift, 3),
            "archetype": archetype, "arche_region": rid, "arche_region_name": rname,
            "arche_sub": sub, "arche_sub_desc": SUBDESC[sub],
            "soulmate": soul, "lights": lights, "dstar": round(dstar, 3), "explore": explore,
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
            conn.commit()
        return prof
    finally:
        conn.close()


# ---------------- 为你推荐(reward 内核) ----------------
def foryou(uid, limit=24, pool=600):
    """reward = aha顿悟(倒U)·calm·info·growth − 厌恶惩罚;在 kept+可向量化作品里排序。"""
    conn = _conn(); cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT vec,spread,dstar FROM mu_profile WHERE uid=%s", (uid,))
        p = cur.fetchone()
        if not p or not p["vec"]:
            prof = compute_profile(uid)
            if not prof.get("ready"):
                return {"ready": False, "items": []}
            mu = prof["vec"]; dstar = prof["dstar"]
        else:
            mu = p["vec"]; dstar = p["dstar"]
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
        scored = []
        for r in cur.fetchall():
            if r["work_id"] in seen:
                continue
            v = work_vec(r["vlm"])
            if v is None:
                continue
            d = dKG(v, mu)
            aha = math.exp(-((d - dstar) ** 2) / (2 * sigma * sigma))
            ar = v[10] if v[10] is not None else 0.5
            calm = _clamp(1 - abs(ar - 0.34))
            qc = float(r["qc"]) if r["qc"] is not None else 0.5
            tot = 0.55 * aha + 0.15 * calm + 0.30 * qc
            scored.append((tot, d, r))
        scored.sort(key=lambda t: -t[0])
        items = []
        for tot, d, r in scored[:limit]:
            items.append({"work_id": r["work_id"], "title": r["title"],
                          "artist": r["name_cn"] or r["name_en"], "cos_key": r["cos_key"],
                          "thumb": img_url(r["cos_key"], 360), "img": img_url(r["cos_key"]),
                          "score": round(tot, 3), "dist": round(d, 3)})
        return {"ready": True, "items": items}
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
