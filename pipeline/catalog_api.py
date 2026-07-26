#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aha 核心资产只读目录 API（连 Postgres,投影给前端,几十万图也不崩）。

- /healthz
- /facets               筛选维度计数(画派/来源/情绪锚/状态)
- /works?...            分页列表(缩略图URL+轻字段),供海量浏览(gallery)
- /work/{id}            单件完整 V2 标注(供 kg-artworks 深读)

图走腾讯云 COS 公网 URL;缩略图用数据万象 imageMogr2(已实测可用,2.3MB→86KB)。
跑: uvicorn catalog_api:app --host 127.0.0.1 --port 8094
nginx: location ^~ /cat/ { proxy_pass http://127.0.0.1:8094/; }
"""
import os, json
from urllib.parse import quote
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor

import _profile_aha as aha_profile  # 审美档案/推荐引擎(同目录;原 profile.py 已改名避开 stdlib)
_d = json.load(open(os.path.expanduser("~/.aha_pg.json")))
POOL = ThreadedConnectionPool(1, 8, host=_d["host"], port=_d["port"], dbname=_d["dbname"],
                              user=_d["user"], password=_d["password"])
COS_BASE = "/img/"  # 同源代理(nginx /img/ → COS 内网端点),规避浏览器 PNA 拦截内网IP

app = FastAPI(title="aha catalog")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

def q(sql, args=(), one=False):
    cn = POOL.getconn()
    try:
        cur = cn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, args if args else None)  # 无参传 None,避免 SQL 里字面 % 被当占位符
        rows = cur.fetchall()
        cn.commit()
        return (rows[0] if rows else None) if one else rows
    finally:
        POOL.putconn(cn)

def ex(sql, args=()):
    cn = POOL.getconn()
    try:
        cur = cn.cursor(); cur.execute(sql, args if args else None); n = cur.rowcount; cn.commit(); return n
    finally:
        POOL.putconn(cn)

@app.middleware("http")
async def audit_mw(request, call_next):
    resp = await call_next(request)
    try:
        p = request.url.path
        if request.method == "POST" and p.startswith("/admin/") and resp.status_code < 400:
            actor = request.headers.get("x-forwarded-user") or request.headers.get("remote-user") or "admin"
            ex("INSERT INTO admin_log(action,query,actor) VALUES(%s,%s,%s)",
               (p.replace("/admin/", ""), str(request.url.query)[:500], actor))
    except Exception:
        pass
    return resp

# slug(canonical 标准码,如 baroque) -> 代表 STYLE 富节点 id(供画作页跳风格库 kg-style-detail)。
# 一个 slug 对应多个富节点(组粒度,如 baroque→意大利/佛兰德斯/西班牙巴洛克),这里取一个代表:
# conf=high 优先、西方优先(真实作品 99.8% 西方)、再按 sort。懒构建一次,缓存。
_STYLE_NODE_BY_SLUG = None
def style_node_for(slug):
    global _STYLE_NODE_BY_SLUG
    if _STYLE_NODE_BY_SLUG is None:
        try:
            rows = q("""SELECT DISTINCT ON (canonical) canonical, style_id
                        FROM style_nodes WHERE canonical IS NOT NULL
                        ORDER BY canonical, (conf='high') DESC, (region='west') DESC,
                                 sort NULLS LAST, style_id""")
            _STYLE_NODE_BY_SLUG = {r["canonical"]: r["style_id"] for r in rows}
        except Exception:
            _STYLE_NODE_BY_SLUG = {}
    return _STYLE_NODE_BY_SLUG.get(slug) if slug else None

THUMB_MAP = {}   # 超大原图(>32MB,imageMogr2处理不了) cos_key -> 预生成缩略图 key
def load_thumb_map():
    global THUMB_MAP
    try:
        THUMB_MAP = {r["orig_key"]: r["thumb_key"] for r in q("SELECT orig_key,thumb_key FROM file_thumb")}
    except Exception:
        THUMB_MAP = {}
load_thumb_map()

def img_url(cos_key, thumb=None):
    if not cos_key: return None
    if cos_key.startswith("img/"):       # demo226 本地图:走 nginx 静态根,不加 COS/imageMogr2
        return "/" + cos_key
    key = THUMB_MAP.get(cos_key, cos_key) # 超大图改指预生成缩略图(imageMogr2 才处理得了)
    u = COS_BASE + quote(key, safe="/")
    return u + f"?imageMogr2/thumbnail/{thumb}x" if thumb else u

def _resolve_wid(token):
    """馆藏码双轨解析:纯数字=旧 work_id;否则=6位馆藏码(首位字母,永不与数字撞)。返回 work_id 或 None。"""
    if token is None: return None
    t = str(token).strip().upper()
    if t.isdigit():
        return int(t)
    r = q("SELECT work_id FROM works WHERE accession_code=%s", (t,), one=True)
    return r["work_id"] if r else None

@app.get("/healthz")
def healthz():
    r = q("SELECT count(*) n FROM works", one=True)
    return {"ok": True, "works": r["n"]}

@app.get("/facets")
def facets(status: str = "kept"):
    def grp(col):
        return [{"k": r["k"], "n": r["n"]} for r in q(
            f"SELECT {col} k, count(*) n FROM works WHERE status=%s AND {col} IS NOT NULL "
            f"GROUP BY {col} ORDER BY 2 DESC LIMIT 60", (status,))]
    statuses = [{"k": r["k"], "n": r["n"]} for r in q(
        "SELECT status k, count(*) n FROM works GROUP BY status ORDER BY 2 DESC")]
    style = [{"k": r["k"], "zh": r["zh"], "en": r["en"], "n": r["n"]} for r in q(
        "SELECT w.style_id k, s.name_zh zh, s.name_en en, count(*) n FROM works w "
        "JOIN styles s ON s.style_id=w.style_id WHERE w.status=%s "
        "GROUP BY w.style_id, s.name_zh, s.name_en, s.sort ORDER BY s.sort", (status,))]
    return {"status": statuses, "style": style, "source": grp("source_batch"),
            "anchor": [{"k": r["k"], "n": r["n"]} for r in q(
                "SELECT vlm->'affect'->>'primary_anchor' k, count(*) n FROM works "
                "WHERE status=%s AND vlm IS NOT NULL GROUP BY 1 ORDER BY 2 DESC", (status,)) if r["k"]]}

@app.get("/works")
def works(status: str = "kept", source: str = None, style: str = None, anchor: str = None,
          q_: str = Query(None, alias="q"), thumb: int = 400,
          offset: int = 0, limit: int = Query(60, le=200)):
    where = ["w.status = %s"]; args = [status]
    if source: where.append("w.source_batch = %s"); args.append(source)
    if style: where.append("w.style_id = %s"); args.append(style)
    if anchor: where.append("w.vlm->'affect'->>'primary_anchor' = %s"); args.append(anchor)
    if q_:
        where.append("(w.title ILIKE %s OR a.name_cn ILIKE %s OR a.name_en ILIKE %s)")
        like = f"%{q_}%"; args += [like, like, like]
    wsql = " AND ".join(where)
    total = q(f"SELECT count(*) n FROM works w JOIN artists a ON a.artist_id=w.artist_id WHERE {wsql}",
              args, one=True)["n"]
    rows = q(f"""SELECT w.work_id, w.accession_code, w.title, a.name_cn, a.name_en, w.year, w.quality,
                        s.name_zh style_zh,
                        w.vlm->'affect'->>'primary_anchor' anchor,
                        f.cos_key, f.width, f.height
                 FROM works w JOIN artists a ON a.artist_id=w.artist_id
                 JOIN files f ON f.file_id=w.primary_file_id
                 LEFT JOIN styles s ON s.style_id=w.style_id
                 WHERE {wsql} ORDER BY w.quality DESC NULLS LAST, w.work_id
                 OFFSET %s LIMIT %s""", args + [offset, limit])
    items = [{"id": r["work_id"], "code": r["accession_code"], "title": r["title"],
              "artist": r["name_cn"] or r["name_en"], "year": r["year"],
              "style": r["style_zh"], "quality": r["quality"], "anchor": r["anchor"],
              "thumb": img_url(r["cos_key"], thumb), "full": img_url(r["cos_key"]),
              "w": r["width"], "h": r["height"]} for r in rows]
    return {"total": total, "offset": offset, "limit": limit, "items": items}

@app.get("/ledger")
def ledger(source: str = None, east_west: str = None, res_tier: str = None,
           artist: str = None, style: int = None, q_: str = Query(None, alias="q"), min_meta: float = 0.0,
           exclude_placeholder: bool = True, thumb: int = 400,
           offset: int = 0, limit: int = Query(60, le=200)):
    """治理总账 v_ledger 的可逛画廊端点:每幅唯一画(非dup)一行,带规范元数据+治理标记。"""
    where = ["cos_key IS NOT NULL"]; args = []
    if artist: where.append("canonical_artist_id = %s"); args.append(artist)
    if style is not None: where.append("style_canon_id = %s"); args.append(style)
    if source: where.append("source = %s"); args.append(source)
    if east_west: where.append("east_west = %s"); args.append(east_west)
    if res_tier: where.append("res_tier = %s"); args.append(res_tier)
    if exclude_placeholder: where.append("(is_placeholder IS NULL OR is_placeholder = false)")
    if min_meta: where.append("meta_score >= %s"); args.append(min_meta)
    if q_:
        where.append("(title ILIKE %s OR name_cn ILIKE %s OR name_en ILIKE %s)")
        like = f"%{q_}%"; args += [like, like, like]
    wsql = " AND ".join(where)
    total = q(f"SELECT count(*) n FROM v_ledger WHERE {wsql}", args, one=True)["n"]
    rows = q(f"""SELECT work_id, title, COALESCE(name_cn,name_en) artist, year, school,
                        east_west, res_tier, meta_score, source, cos_key, px
                 FROM v_ledger WHERE {wsql}
                 ORDER BY meta_score DESC NULLS LAST, work_id
                 OFFSET %s LIMIT %s""", args + [offset, limit])
    items = [{"id": r["work_id"], "title": r["title"], "artist": r["artist"], "year": r["year"],
              "school": r["school"], "east_west": r["east_west"], "res_tier": r["res_tier"],
              "source": r["source"], "thumb": img_url(r["cos_key"], thumb), "full": img_url(r["cos_key"])}
             for r in rows]
    return {"total": total, "offset": offset, "limit": limit, "items": items}

@app.get("/style_artists")
def style_artists(style: int, limit: int = Query(80, le=300), offset: int = 0):
    """某规范流派下的艺术家(按作品数排)——'印象派的画家有谁'。"""
    total = q("SELECT count(*) n FROM artist_assoc WHERE primary_style=%s", (style,), one=True)["n"]
    rows = q("""SELECT aa.artist_id, aa.name_cn, aa.name_en, aa.n_works, aa.born, aa.death, aa.region, aa.east_west,
                  (SELECT f.cos_key FROM v_ledger v JOIN files f ON f.file_id=(SELECT primary_file_id FROM works WHERE work_id=v.work_id)
                   WHERE v.canonical_artist_id=aa.artist_id ORDER BY v.meta_score DESC NULLS LAST LIMIT 1) cos
                FROM artist_assoc aa WHERE aa.primary_style=%s ORDER BY aa.n_works DESC LIMIT %s OFFSET %s""",
             (style, limit, offset))
    items = [{"artist_id": r["artist_id"], "name": r["name_cn"] or r["name_en"], "works": r["n_works"],
              "born": r["born"], "death": r["death"], "region": r["region"], "east_west": r["east_west"],
              "thumb": img_url(r["cos"], 300)} for r in rows]
    return {"total": total, "items": items}

@app.get("/origin_map")
def origin_map(min_n: int = 1):
    """艺术家来源地图:出生地→坐标+艺术家数+代表艺术家。"""
    rows = q("""WITH a AS (
        SELECT aa.artist_id, aa.name_cn, aa.n_works,
               trim(regexp_replace(aa.region, '[\\[\\(，,].*$', '')) place
        FROM artist_assoc aa WHERE aa.region IS NOT NULL AND aa.region<>'')
      SELECT pg.name, pg.lat, pg.lng, pg.country, count(*) n,
             (array_agg(a.name_cn ORDER BY a.n_works DESC))[1:3] top
      FROM a JOIN place_geo pg ON pg.name=a.place
      GROUP BY pg.name,pg.lat,pg.lng,pg.country HAVING count(*)>=%s
      ORDER BY count(*) DESC""", (min_n,))
    pts = [{"name": r["name"], "lat": r["lat"], "lng": r["lng"], "country": r["country"],
            "n": r["n"], "top": [x for x in r["top"] if x]} for r in rows]
    return {"points": pts, "total_cities": len(pts), "total_artists": sum(p["n"] for p in pts)}

@app.get("/assoc/artist")
def assoc_artist(id: str):
    """艺术家关联详情:流派分布/年代/出生地/同代人。"""
    a = q("SELECT * FROM artist_assoc WHERE artist_id=%s", (id,), one=True)
    if not a: return {"found": False}
    a = dict(a)
    contemporaries = []
    if a.get("born"):
        contemporaries = [dict(r) for r in q("""SELECT name_cn,name_en,born,death,primary_style_cn,n_works
            FROM artist_assoc WHERE artist_id<>%s AND born IS NOT NULL
              AND born <= %s AND COALESCE(death,born+80) >= %s AND primary_style=%s
            ORDER BY n_works DESC LIMIT 8""", (id, (a["death"] or a["born"]+80), a["born"], a.get("primary_style")))]
    return {"found": True, "artist": a, "contemporaries": contemporaries}

@app.get("/styles")
def styles_public():
    """公开:规范流派词表+各流派作品数(供前台流派筛选)。"""
    return {"styles": [dict(r) for r in q("""SELECT sc.canon_id, sc.name_cn, sc.name_en,
        count(v.work_id) n FROM style_canon sc
        LEFT JOIN v_ledger v ON v.style_canon_id=sc.canon_id
        WHERE sc.canon_id<>0 GROUP BY sc.canon_id,sc.name_cn,sc.name_en,sc.sort
        HAVING count(v.work_id)>0 ORDER BY sc.sort""")]}

@app.get("/ledger_artists")
def ledger_artists(q_: str = Query(None, alias="q"), east_west: str = None, city: str = None,
                   offset: int = 0, limit: int = Query(60, le=200)):
    """按作品数逛全量规范艺术家(归并后);每位带一张样图缩略。city=出生地筛(地图检索)。"""
    where = ["canonical_artist_id IS NOT NULL", "canonical_artist_id NOT LIKE '%%unknown%%'",
             "COALESCE(name_cn,name_en) IS NOT NULL"]; args = []
    if east_west: where.append("east_west = %s"); args.append(east_west)
    if city: where.append("canonical_artist_id IN (SELECT artist_id FROM artist_assoc WHERE trim(regexp_replace(region,'[\\[\\(，,].*$','')) = %s)"); args.append(city)
    if q_:
        where.append("(name_cn ILIKE %s OR name_en ILIKE %s)"); like = f"%{q_}%"; args += [like, like]
    wsql = " AND ".join(where)
    total = q(f"SELECT count(*) n FROM (SELECT 1 FROM v_ledger WHERE {wsql} GROUP BY canonical_artist_id) z",
              args, one=True)["n"]
    rows = q(f"""SELECT canonical_artist_id aid, max(COALESCE(name_cn,name_en)) name,
                        max(name_en) en, max(east_west) ew, count(*) n, max(aha_kg_id) kg,
                        (array_agg(cos_key ORDER BY meta_score DESC NULLS LAST))[1] cos
                 FROM v_ledger WHERE {wsql}
                 GROUP BY canonical_artist_id ORDER BY count(*) DESC, name
                 OFFSET %s LIMIT %s""", args + [offset, limit])
    items = [{"artist_id": r["aid"], "name": r["name"], "en": r["en"], "east_west": r["ew"],
              "works": r["n"], "kg": r["kg"], "thumb": img_url(r["cos"], 300)} for r in rows]
    return {"total": total, "offset": offset, "limit": limit, "items": items}

@app.get("/stats")
def stats():
    totals = q("""SELECT (SELECT count(*) FROM works) works,(SELECT count(*) FROM files) files,
                         (SELECT count(*) FROM artists) artists,(SELECT count(*) FROM styles) styles,
                         (SELECT count(*) FROM works WHERE status<>'dup') uniq""", one=True)
    status = [{"k": r["k"], "n": r["n"]} for r in q(
        "SELECT status k, count(*) n FROM works GROUP BY status ORDER BY 2 DESC")]
    # 每来源:总量 / 已过闸 / 入核心资产
    src = [{"k": r["k"], "total": r["total"], "gated": r["gated"], "kept": r["kept"]} for r in q(
        """SELECT split_part(source_batch,':',1) k, count(*) total,
                  count(*) FILTER (WHERE status NOT IN ('pending','dup')) gated,
                  count(*) FILTER (WHERE status='kept') kept
           FROM works GROUP BY 1 ORDER BY 2 DESC""")]
    style = [{"zh": r["zh"], "n": r["n"]} for r in q(
        """SELECT s.name_zh zh, count(*) n FROM works w JOIN styles s ON s.style_id=w.style_id
           WHERE w.status='kept' GROUP BY s.name_zh, s.sort ORDER BY s.sort""")]
    anchor = [{"k": r["k"], "n": r["n"]} for r in q(
        "SELECT vlm->'affect'->>'primary_anchor' k, count(*) n FROM works WHERE status='kept' AND vlm IS NOT NULL GROUP BY 1 ORDER BY 2 DESC") if r["k"]]
    qhist = [{"b": r["b"], "n": r["n"]} for r in q(
        """SELECT (floor(quality*10)/10)::text b, count(*) n FROM works WHERE status='kept' AND quality IS NOT NULL GROUP BY 1 ORDER BY 1""")]
    pace = q("""SELECT count(*) FILTER (WHERE reviewed_at > now()-interval '1 hour') h1,
                       count(*) FILTER (WHERE reviewed_at > now()-interval '24 hour') h24
                FROM works WHERE reviewed_at IS NOT NULL""", one=True)
    curatable = totals["works"] - next((s["n"] for s in status if s["k"] == "dup"), 0)
    gated = sum(s["n"] for s in status if s["k"] in ("kept", "archived", "rejected"))
    recent = [{"title": r["title"], "artist": r["a"], "reason": r["reject_reason"],
               "status": r["status"], "thumb": img_url(r["cos_key"], 200)} for r in q(
        """SELECT w.title, a.name_cn a, w.reject_reason, w.status, f.cos_key
           FROM works w JOIN artists a ON a.artist_id=w.artist_id JOIN files f ON f.file_id=w.primary_file_id
           WHERE w.status IN ('rejected','archived') ORDER BY w.reviewed_at DESC NULLS LAST LIMIT 18""")]
    return {"totals": totals, "status": status, "source": src, "style": style, "anchor": anchor,
            "qhist": qhist, "pace": pace,
            "gating": {"curatable": curatable, "gated": gated, "pending": totals["works"] - gated -
                       next((s["n"] for s in status if s["k"] == "dup"), 0),
                       "pct": round(gated * 100.0 / curatable, 2) if curatable else 0},
            "recent": recent}

@app.get("/governance")
def governance():
    """数据治理元信息:直接从运行中的脚本读取真实提示词/规则(source-of-truth,不会脱节)。"""
    import sys, os as _os, inspect
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "scripts"))
    import gate, style_norm
    # 从 _vlm_call 源码里抽 max_tokens / 默认 max_px(避免硬编码脱节)
    src = inspect.getsource(gate._vlm_call)
    import re as _re
    mt = _re.search(r"max_tokens=(\d+)", src)
    px = _re.search(r"max_px=(\d+)", inspect.getsource(gate.vlm)) or _re.search(r"max_px=(\d+)", inspect.getsource(gate._img_b64))
    return {
        "model": "mimo-v2.5（小米，推理模型，Anthropic 格式端点）",
        "image_px": int(px.group(1)) if px else 768,
        "max_tokens": int(mt.group(1)) if mt else None,
        "prompt": gate.GATE_PROMPT,
        "anchors": gate.ANCHORS.split(),
        "category_map": {
            "kept(绘画·核心资产)": sorted(gate.CAT_KEPT),
            "archived(非绘画·单独归档)": sorted(gate.CAT_ARCHIVE),
            "rejected(垃圾·剔除)": sorted(gate.CAT_REJECT),
        },
        "dedup": {"sha256": "精确重复·入库即挡", "phash_hamming": "≤6 近重复聚类·每簇留高清/已标注主图",
                  "scope": "全库跨来源 xdedup.py", "min_side_px": 200},
        "styles": [{"id": c[0], "zh": c[1], "en": c[2]} for c in style_norm.CANON],
        "style_rules": [[rx.pattern, sid] for rx, sid in style_norm._COMPILED],
        "stages": [
            ["①入库", "每来源一个适配器→统一三表(artists/works/files)；sha256/phash指纹；cos_key唯一保幂等"],
            ["②规范", "style_norm.py 关键词规则把杂乱画派归一到 31 规范风格(中文为主+英文+i18n)"],
            ["③去重", "xdedup.py 全库跨源 phash 近重复，留主图，其余 status=dup"],
            ["④过闸", "gate.py 调 mimo 一次出『策展分类+质量+加强版V2标注』，三路分流"],
            ["⑤投影", "catalog_api 只读 API + COS缩略图 → 画廊/看板"],
        ],
        "principles": [
            "软策展两层：素材层(pending) ↔ 核心资产(kept)，**永不物理删原图**，剔除=不晋升、可回溯",
            "非绘画(雕塑/器物)不删，单独归档 archived 供后期用",
            "标注 schema 对齐线上 kg_artwork_v2，画廊深读直接复用",
            "identify 只在确信认出名画时填作者/标题，否则留空不臆造",
        ],
    }

@app.get("/anomalies")
def anomalies(sample: int = 12):
    """异常雷达:自动挑出可疑标注/治理问题,每类给计数+样本,供人工抽查纠错。"""
    def run(where, label, key, extra="NULL::text"):
        n = q(f"SELECT count(*) c FROM works w JOIN artists a ON a.artist_id=w.artist_id WHERE {where}", one=True)["c"]
        rows = q(f"""SELECT w.work_id, w.title, a.name_cn, a.name_en, w.status, w.quality,
                            f.cos_key, ({extra}) note
                     FROM works w JOIN artists a ON a.artist_id=w.artist_id
                     LEFT JOIN files f ON f.file_id=w.primary_file_id
                     WHERE {where} ORDER BY w.work_id LIMIT {int(sample)}""")
        return {"key": key, "label": label, "count": n,
                "samples": [{"id": r["work_id"], "title": r["title"],
                             "artist": r["name_cn"] or r["name_en"], "status": r["status"],
                             "note": r["note"], "thumb": img_url(r["cos_key"], 200)} for r in rows]}
    out = []
    out.append(run("w.status='kept' AND w.quality < 0.45", "低质却入核心资产(quality<0.45)", "lowq_kept",
                   "'q='||w.quality"))
    out.append(run("w.status='kept' AND w.is_artwork = false", "kept 但 VLM 说非完整画作", "kept_notart"))
    out.append(run("w.status='kept' AND (NOT w.vlm ? 'fused' OR NOT w.vlm ? 'language7' OR NOT w.vlm ? 'affect')",
                   "kept 但标注缺字段(fused/language7/affect)", "missing_fields"))
    out.append(run("w.status='kept' AND w.vlm ? 'style_mix' AND "
                   "(SELECT abs(coalesce(sum((e->>'pct')::float),0)-100) FROM jsonb_array_elements(w.vlm->'style_mix') e) > 15",
                   "style_mix 占比合计偏离100%>15", "stylemix_bad",
                   "(SELECT coalesce(sum((e->>'pct')::float),0) FROM jsonb_array_elements(w.vlm->'style_mix') e)::text"))
    out.append(run("w.status='pending' AND w.reject_reason LIKE 'err:%'", "过闸残留错误(卡住待重试)", "err_pending",
                   "left(w.reject_reason,40)"))
    # identify 存疑:有真实作者却与高置信 identify 不符(可能 VLM 幻觉,也可能源错)
    out.append(run("(w.vlm->'identify'->>'known')='true' AND (w.vlm->'identify'->>'confidence')::float>=0.8 "
                   "AND a.name_cn IS NOT NULL AND a.artist_id NOT LIKE 'yishujia%' "
                   "AND NOT (a.name_cn LIKE '%'||split_part(w.vlm->'identify'->>'artist',' ',1)||'%')",
                   "identify 与来源作者不符(疑幻觉)", "identify_suspect",
                   "'VLM认:'||(w.vlm->'identify'->>'artist')"))
    out.append(run("w.status='archived' AND (w.vlm->>'media' ILIKE '%油画%' OR w.vlm->>'media' ILIKE '%布面%')",
                   "归档为非绘画但 media 像油画(疑误判)", "archived_maybe_painting", "w.vlm->>'media'"))
    return {"types": out, "scanned_gated": q("SELECT count(*) c FROM works WHERE status NOT IN ('pending','dup')", one=True)["c"]}

# ================= admin（写操作，nginx basic-auth 保护 /cat/admin/）=================
import subprocess as _sp
VALID_STATUS = {"kept", "archived", "rejected", "pending", "dup"}

@app.post("/admin/status")
def admin_set_status(id: int, status: str, reason: str = "manual"):
    """人工纠错:覆盖某件的策展状态(promote/demote),记 reject_reason 留痕。"""
    if status not in VALID_STATUS: raise HTTPException(400, "bad status")
    n = ex("UPDATE works SET status=%s, reject_reason=%s, reviewed_at=now() WHERE work_id=%s",
           (status, f"manual:{reason}", id))
    return {"ok": bool(n), "id": id, "status": status}

@app.post("/admin/regate")
def admin_regate(id: int):
    """标记重标:置回 pending,下轮过闸会重新标注(旧 vlm 暂留,过闸后覆盖)。"""
    n = ex("UPDATE works SET status='pending', reject_reason='requeue' WHERE work_id=%s", (id,))
    return {"ok": bool(n), "id": id}

@app.get("/admin/review")
def admin_review(n: int = 12, status: str = "kept"):
    """抽检:随机抽 n 件供人眼核(默认核心资产 kept)。"""
    rows = q("""SELECT w.work_id, w.title, a.name_cn, a.name_en, w.status, w.quality,
                       w.vlm->>'category' cat, w.vlm->'affect'->>'primary_anchor' anchor,
                       f.cos_key FROM works w JOIN artists a ON a.artist_id=w.artist_id
                JOIN files f ON f.file_id=w.primary_file_id
                WHERE w.status=%s ORDER BY random() LIMIT %s""", (status, n))
    return {"items": [{"id": r["work_id"], "title": r["title"], "artist": r["name_cn"] or r["name_en"],
                       "status": r["status"], "quality": r["quality"], "cat": r["cat"], "anchor": r["anchor"],
                       "thumb": img_url(r["cos_key"], 300)} for r in rows]}

@app.get("/admin/gate_status")
def admin_gate_status():
    try:
        running = bool(_sp.run(["pgrep", "-f", "gate.py vlm"], capture_output=True).stdout.strip())
    except Exception:
        running = False
    pend = q("SELECT count(*) c FROM works WHERE status='pending'", one=True)["c"]
    p10 = q("SELECT count(*) c FROM works WHERE reviewed_at>now()-interval '10 min'", one=True)["c"]
    bysrc = [{"k": r["k"], "pending": r["c"]} for r in q(
        "SELECT split_part(source_batch,':',1) k, count(*) c FROM works WHERE status='pending' GROUP BY 1 ORDER BY 2 DESC")]
    exh = q("SELECT count(*) c FROM works WHERE exhibited", one=True)["c"]
    exhwv = q("SELECT count(*) c FROM works WHERE exhibited AND vlm ? 'worldview'", one=True)["c"]
    return {"running": running, "pending": pend, "rate_10min": p10, "by_source": bysrc,
            "exhibited": exh, "exhibited_ready": exhwv}

@app.post("/admin/run_gate")
def admin_run_gate(source: str = None, limit: int = 1000, workers: int = 8):
    if _sp.run(["pgrep", "-f", "gate.py vlm"], capture_output=True).stdout.strip():
        return {"ok": False, "msg": "已有过闸进程在跑"}
    args = ["python3", "-u", "scripts/gate.py", "vlm", "--workers", str(workers), "--limit", str(int(limit))]
    if source: args += ["--source", source]
    log = open("/tmp/gate_admin.log", "a")
    _sp.Popen(args, cwd=os.path.dirname(__file__), stdout=log, stderr=log, start_new_session=True)
    return {"ok": True, "cmd": " ".join(args)}

@app.post("/admin/stop_gate")
def admin_stop_gate():
    _sp.run(["pkill", "-9", "-f", "gate.py vlm"])
    return {"ok": True}

@app.post("/admin/exhibit")
def admin_exhibit(id: int, on: bool = True):
    """人工选图:单件入展/下架(仅 kept 可入展)。"""
    n = ex("UPDATE works SET exhibited=%s, exhibit_at=CASE WHEN %s THEN now() ELSE NULL END "
           "WHERE work_id=%s AND status='kept'", (on, on, id))
    _EXH_CACHE.clear()   # 展出集变了,清缓存让首页即时反映
    return {"ok": bool(n), "id": id, "exhibited": on}

@app.post("/admin/auto_exhibit")
def admin_auto_exhibit(min_quality: float = 0.6, per_artist: int = 0, clear: bool = False):
    """规则A 自动入展:kept 且 composite 质量≥阈值;per_artist>0 时每艺术家按质量取前 N(均衡)。"""
    if clear: ex("UPDATE works SET exhibited=false, exhibit_at=NULL WHERE exhibited")
    if per_artist and per_artist > 0:
        ex("""WITH r AS (SELECT work_id, row_number() OVER (PARTITION BY artist_id ORDER BY quality DESC NULLS LAST) rn
                 FROM works WHERE status='kept' AND quality>=%s)
             UPDATE works w SET exhibited=true, exhibit_at=now() FROM r
             WHERE w.work_id=r.work_id AND r.rn<=%s AND NOT w.exhibited""", (min_quality, per_artist))
    else:
        ex("UPDATE works SET exhibited=true, exhibit_at=now() WHERE status='kept' AND quality>=%s AND NOT exhibited",
           (min_quality,))
    cnt = q("SELECT count(*) c FROM works WHERE exhibited", one=True)["c"]
    _EXH_CACHE.clear()   # 展出集变了,清缓存让首页即时反映
    return {"ok": True, "min_quality": min_quality, "per_artist": per_artist, "exhibited_total": cnt}

# ---- 模块数据(后台各板块,均 nginx auth 保护 /cat/admin/) ----
@app.get("/admin/m/exhibit")
def m_exhibit():
    t = q("""SELECT count(*) FILTER (WHERE exhibited) e,
                    count(*) FILTER (WHERE exhibited AND vlm ? 'worldview') r,
                    count(*) FILTER (WHERE status='kept') k FROM works""", one=True)
    bystyle = [{"k": r["zh"], "n": r["n"]} for r in q(
        "SELECT s.name_zh zh,count(*) n FROM works w JOIN styles s ON s.style_id=w.style_id WHERE w.exhibited GROUP BY s.name_zh,s.sort ORDER BY s.sort")]
    bysrc = [{"k": r["k"], "n": r["n"]} for r in q(
        "SELECT split_part(source_batch,':',1) k,count(*) n FROM works WHERE exhibited GROUP BY 1 ORDER BY 2 DESC")]
    recent = [{"id": r["work_id"], "title": r["title"], "artist": r["name_cn"] or r["name_en"],
               "thumb": img_url(r["cos_key"], 200)} for r in q(
        """SELECT w.work_id,w.title,a.name_cn,a.name_en,f.cos_key FROM works w JOIN artists a ON a.artist_id=w.artist_id
           JOIN files f ON f.file_id=w.primary_file_id WHERE w.exhibited ORDER BY w.exhibit_at DESC NULLS LAST LIMIT 30""")]
    cols = [{"id": r["collection_id"], "name": r["name"], "n": r["n"]} for r in q(
        "SELECT c.collection_id,c.name,count(cw.work_id) n FROM collections c LEFT JOIN collection_works cw ON cw.collection_id=c.collection_id GROUP BY c.collection_id,c.name ORDER BY c.sort,c.collection_id")]
    return {"totals": t, "by_style": bystyle, "by_source": bysrc, "recent": recent, "collections": cols}

@app.post("/admin/collection/create")
def col_create(name: str, description: str = None, owner_uid: str = "official", kind: str = "theme", is_public: bool = True):
    r = q("""INSERT INTO collections(name,description,owner_uid,kind,is_public)
             VALUES(%s,%s,%s,%s,%s) RETURNING collection_id""",
          (name, description, owner_uid, kind, is_public), one=True)
    return {"ok": True, "id": r["collection_id"]}
@app.post("/admin/collection/add")
def col_add(cid: int, id: int):
    ex("INSERT INTO collection_works(collection_id,work_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (cid, id))
    return {"ok": True}
@app.post("/admin/collection/delete")
def col_delete(cid: int):
    ex("DELETE FROM collections WHERE collection_id=%s", (cid,)); return {"ok": True}

@app.get("/admin/m/artists")
def m_artists(q_: str = Query(None, alias="q")):
    t = q("""SELECT count(*) total, count(*) FILTER (WHERE born IS NOT NULL) with_born,
                    count(*) FILTER (WHERE name_cn IS NULL OR name_cn='') no_cn FROM artists""", one=True)
    bysrc = [{"k": r["k"], "n": r["n"]} for r in q(
        "SELECT split_part(artist_id,':',1) k,count(*) n FROM artists GROUP BY 1 ORDER BY 2 DESC")]
    if q_:
        rows = q("""SELECT a.artist_id,a.name_cn,a.name_en,a.born,a.death,count(w.work_id) n
                    FROM artists a LEFT JOIN works w ON w.artist_id=a.artist_id
                    WHERE a.name_cn ILIKE %s OR a.name_en ILIKE %s GROUP BY a.artist_id,a.name_cn,a.name_en,a.born,a.death
                    ORDER BY n DESC LIMIT 40""", (f"%{q_}%", f"%{q_}%"))
    else:
        rows = q("""SELECT a.artist_id,a.name_cn,a.name_en,a.born,a.death,count(w.work_id) n
                    FROM artists a JOIN works w ON w.artist_id=a.artist_id WHERE w.status<>'dup'
                    GROUP BY a.artist_id,a.name_cn,a.name_en,a.born,a.death ORDER BY n DESC LIMIT 40""")
    items = [{"id": r["artist_id"], "cn": r["name_cn"], "en": r["name_en"],
              "born": r["born"], "death": r["death"], "n": r["n"]} for r in rows]
    return {"totals": t, "by_source": bysrc, "items": items}

@app.get("/admin/m/canon")
def m_canon():
    """策展艺术家(283 位,有完整主页的那批)统计 / 分布 / 达标缺口 / 考据状态。
    区别于 /admin/m/artists(那个是 7900+ 条源艺术家)。"""
    cnts = {r["aha_kg_id"]: r["n"] for r in q(
        "SELECT a.aha_kg_id, count(*) n FROM works w JOIN artists a ON a.artist_id=w.artist_id "
        "WHERE w.status='kept' AND a.aha_kg_id IS NOT NULL GROUP BY a.aha_kg_id")}
    FIELDS = {
        "师承": lambda L: bool(L.get("teachers")) or bool(L.get("students")),
        "七大构成": lambda L: len(L.get("lang") or {}) >= 7,
        "情绪VAD": lambda L: all((L.get("affect") or {}).get(k) is not None for k in ("v","a","d")),
        "离散σ": lambda L: (L.get("wv") or {}).get("spread") is not None,
        "轨迹坐标": lambda L: any(p.get("x") is not None for p in (L.get("trajectory") or [])),
        "代表作点云": lambda L: bool(L.get("works")),
        "画外音": lambda L: bool(L.get("voice_echo")),
        "题材": lambda L: bool(L.get("subjects")),
    }
    total = with_port = with_works = complete = 0
    by_region = {"west": 0, "east": 0}; by_wv = {}; era_b = {}
    fcov = {k: 0 for k in FIELDS}; verify_c = {}; suspects = []
    gaps = {"no_teachers": [], "no_works": [], "no_portrait": [], "incomplete": []}
    ERA = [(-9999,0,"上古"),(1,900,"古典·汉唐"),(901,1300,"中世·宋元"),(1301,1600,"文艺复兴·明"),
           (1601,1800,"巴洛克·清"),(1801,1900,"19世纪"),(1901,1980,"现代"),(1981,9999,"当代")]
    rows = q("SELECT canon_id, cn, region, born, lore FROM artists_canon")
    for r in rows:
        total += 1; L = r["lore"] or {}; wv = L.get("wv") or {}
        n = cnts.get(r["canon_id"], 0)
        if L.get("portrait"): with_port += 1
        else: gaps["no_portrait"].append({"id": r["canon_id"], "cn": r["cn"]})
        if n > 0: with_works += 1
        else: gaps["no_works"].append({"id": r["canon_id"], "cn": r["cn"]})
        reg = r["region"] if r["region"] in by_region else "west"; by_region[reg] += 1
        rid = wv.get("region_id");
        if rid: by_wv[rid] = by_wv.get(rid, 0) + 1
        born = r["born"]
        if born is None:
            for pt in (L.get("trajectory") or []):
                import re as _r2; m = _r2.search(r"(\d{3,4})", str(pt.get("year") or ""))
                if m: born = int(m.group(1)); break
        if born is not None:
            for a0,b0,lab in ERA:
                if a0 <= born <= b0: era_b[lab] = era_b.get(lab, 0) + 1; break
        missing = []
        for k, f in FIELDS.items():
            if f(L): fcov[k] += 1
            else: missing.append(k)
        if not missing: complete += 1
        else: gaps["incomplete"].append({"id": r["canon_id"], "cn": r["cn"], "missing": missing, "n": n})
        if not (L.get("teachers") or L.get("students")):
            gaps["no_teachers"].append({"id": r["canon_id"], "cn": r["cn"], "n": n})
        vf = L.get("verify") if isinstance(L.get("verify"), dict) else None
        vs = (vf or {}).get("status") if vf else "未核"
        verify_c[vs] = verify_c.get(vs, 0) + 1
        if vs == "疑点" and (vf.get("flags") or []):
            suspects.append({"id": r["canon_id"], "cn": r["cn"], "note": vf.get("note", ""),
                             "flags": vf.get("flags", [])[:4]})
    for g in gaps.values():
        g.sort(key=lambda x: -x.get("n", 0))
    era_list = [{"label": lab, "n": era_b[lab]} for _,_,lab in ERA if lab in era_b]
    return {"total": total, "with_portrait": with_port, "with_works": with_works,
            "works_total": sum(cnts.values()), "complete": complete,
            "by_region": by_region, "by_wv": by_wv, "by_era": era_list,
            "field_coverage": fcov, "verify": verify_c, "suspects": suspects[:60],
            "gaps": {k: v[:40] for k, v in gaps.items()},
            "gap_counts": {k: len(v) for k, v in gaps.items()}}

LIVE_DIR = "/data/pub/p/aha/data/live"
@app.get("/admin/m/projection")
def m_projection():
    import os as _o, time as _t
    slices = []
    if _o.path.isdir(LIVE_DIR):
        for fn in sorted(_o.listdir(LIVE_DIR)):
            if not fn.endswith(".json"): continue
            st = _o.stat(_o.path.join(LIVE_DIR, fn))
            slices.append({"file": fn, "kb": round(st.st_size/1024), "mtime": int(st.st_mtime),
                           "age_min": round((_t.time()-st.st_mtime)/60)})
    db = q("SELECT count(*) FILTER (WHERE status='kept') kept, count(*) FILTER (WHERE exhibited) exh, "
           "count(*) FILTER (WHERE status='kept' AND vlm IS NOT NULL) annotated FROM works", one=True)
    pages = [{"name": "kg-artworks-live", "demo": "kg-artworks", "slice": "artworks_v2.json", "ready": True},
             {"name": "kg-worldview-live", "demo": "kg-worldview-map", "slice": "points.json", "ready": True},
             {"name": "kg-affect-live", "demo": "kg-affect", "slice": "affect.json", "ready": True},
             {"name": "kg-style-live", "demo": "kg-style-vectors", "slice": "styles.json", "ready": True},
             {"name": "kg-artist-live", "demo": "kg-artist-atlas", "slice": "artists.json", "ready": True},
             {"name": "kg-subject-live", "demo": "kg-subject", "slice": "subjects.json", "ready": True}]
    return {"slices": slices, "db": db, "pages": pages}

_PROMPT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "gate_prompt.txt")
@app.get("/admin/prompt")
def get_prompt():
    import sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
    import gate
    override = os.path.exists(_PROMPT_FILE)
    return {"effective": gate.effective_prompt(), "builtin": gate.GATE_PROMPT, "override": override}
@app.post("/admin/prompt")
async def save_prompt(request: Request):
    body = (await request.body()).decode("utf-8")
    if len(body.strip()) < 50: raise HTTPException(400, "提示词过短,拒绝保存")
    open(_PROMPT_FILE, "w", encoding="utf-8").write(body)
    return {"ok": True, "len": len(body)}
@app.post("/admin/prompt/reset")
def reset_prompt():
    if os.path.exists(_PROMPT_FILE): os.remove(_PROMPT_FILE)
    return {"ok": True}
@app.get("/admin/adminpass")
def get_admin_pass():
    """单点登录桥:本路由躺在 nginx basic-auth(/cat/admin/)之后,只有已登录后台者可达。
    返回 ark_gen(8093)用的 admin_pass,供 narrators/archive 等页免二次输口令。"""
    try:
        ap = json.load(open(os.path.expanduser("~/.aha_ark.json"))).get("admin_pass", "")
    except Exception:
        ap = ""
    return {"pass": ap}

@app.post("/admin/collection/add_bulk")
def col_add_bulk(cid: int, style: str = None, source: str = None, limit: int = 200):
    """组卷:把 exhibited 中(可按 style_id / source 过滤)的作品批量加入主题展。"""
    w = ["w.exhibited"]; a = []
    if style: w.append("w.style_id=%s"); a.append(style)
    if source: w.append("w.source_batch LIKE %s"); a.append(source + "%")
    n = ex(f"""INSERT INTO collection_works(collection_id, work_id)
               SELECT %s, w.work_id FROM works w WHERE {' AND '.join(w)} LIMIT %s
               ON CONFLICT DO NOTHING""", [cid] + a + [int(limit)])
    return {"ok": True, "added": n}

@app.post("/admin/reproject")
def reproject(scope: str = "kept", limit: int = 4000):
    base = os.path.dirname(os.path.abspath(__file__))
    r = _sp.run(["python3", "scripts/build_projections.py", "--scope", scope, "--limit", str(int(limit))],
                cwd=base, capture_output=True, text=True, timeout=180)
    _sp.run(f"mkdir -p {LIVE_DIR} && cp -f {base}/../web/data/live/*.json {LIVE_DIR}/", shell=True)
    return {"ok": r.returncode == 0, "out": (r.stdout or "")[-300:], "err": (r.stderr or "")[-200:]}

@app.get("/admin/m/users")
def m_users():
    def c(t): return q(f"SELECT count(*) c FROM {t}", one=True)["c"]
    counts = {k: c(k) for k in ["mu_user", "mu_event", "mu_comment", "mu_rating", "mu_persona", "mu_generation", "mu_taste", "mu_collection"]}
    kinds = [{"k": r["kind"], "n": r["n"]} for r in q("SELECT kind,count(*) n FROM mu_event GROUP BY kind ORDER BY 2 DESC LIMIT 12")]
    # mu_* 的 work_id 是 museum 自己的文本键(与我们 bigint work_id 不同源),不 join
    cmts = [{"body": r["body"], "status": r["status"], "work": r["work_id"]} for r in q(
        "SELECT body,status,work_id FROM mu_comment ORDER BY created DESC LIMIT 20")]
    topc = [{"work": r["work_id"], "n": r["n"]} for r in q(
        "SELECT work_id::text work_id,count(*) n FROM mu_collection GROUP BY work_id ORDER BY 2 DESC LIMIT 12")]
    return {"counts": counts, "event_kinds": kinds, "comments": cmts, "top_collected": topc}

@app.get("/admin/users")
def admin_users(limit: int = 100):
    """用户列表(按最近活跃排):活跃度+档案概览。"""
    rows = q("""SELECT u.uid, u.nickname, u.created, u.admin_note, u.email,
                  u.ip, u.ip_country, u.ip_city, u.ua, u.last_seen, (u.email IS NOT NULL) registered,
                  p.archetype, p.soulmate_cn,
                  count(DISTINCT e.id) n_ev, count(DISTINCT col.work_id) n_col,
                  count(DISTINCT g.id) n_gen, count(DISTINCT cm.id) n_cmt, max(e.ts) last_active
                FROM mu_user u
                LEFT JOIN mu_event e ON e.uid=u.uid
                LEFT JOIN mu_collection col ON col.uid=u.uid
                LEFT JOIN mu_generation g ON g.uid=u.uid
                LEFT JOIN mu_comment cm ON cm.uid=u.uid
                LEFT JOIN mu_profile p ON p.uid=u.uid
                GROUP BY u.uid,u.nickname,u.created,u.admin_note,u.email,u.ip,u.ip_country,u.ip_city,u.ua,u.last_seen,p.archetype,p.soulmate_cn
                ORDER BY COALESCE(u.last_seen, max(e.ts)) DESC NULLS LAST LIMIT %s""", (limit,))
    return {"users": [dict(r) for r in rows]}

@app.get("/admin/user")
def admin_user(uid: str):
    """单个用户全画像:档案/口味/收藏/生成/评论/近期行为。"""
    u = q("SELECT uid,nickname,email,created,admin_note,ua,ip,first_ip,ip_country,ip_city,last_seen FROM mu_user WHERE uid=%s", (uid,), one=True)
    prof = q("""SELECT archetype,arche_region,arche_sub,soulmate_cn,soulmate_aff,spread,lights,dstar,explore,n,updated
                FROM mu_profile WHERE uid=%s""", (uid,), one=True)
    taste = q("SELECT x,y,spread,n,updated FROM mu_taste WHERE uid=%s", (uid,), one=True)
    cols = [dict(r) for r in q("SELECT work_id::text wk, ts FROM mu_collection WHERE uid=%s ORDER BY ts DESC LIMIT 80", (uid,))]
    gens = [dict(r) for r in q("SELECT id,file,prompt,rating,ts FROM mu_generation WHERE uid=%s ORDER BY ts DESC LIMIT 40", (uid,))]
    cmts = [dict(r) for r in q("SELECT id,work_id::text wk,body,kind,status,likes,created FROM mu_comment WHERE uid=%s ORDER BY created DESC LIMIT 40", (uid,))]
    evs = [dict(r) for r in q("SELECT kind,target_type,target_id,work_id::text wk,dwell_ms,ts FROM mu_event WHERE uid=%s ORDER BY ts DESC LIMIT 60", (uid,))]
    return {"user": dict(u) if u else None, "profile": dict(prof) if prof else None,
            "taste": dict(taste) if taste else None, "collections": cols,
            "generations": gens, "comments": cmts, "events": evs}

@app.post("/admin/user/note")
def admin_user_note(uid: str, note: str = ""):
    ex("UPDATE mu_user SET admin_note=%s WHERE uid=%s", (note, uid))
    return {"ok": True, "uid": uid}

@app.post("/admin/comment/moderate")
def admin_comment_moderate(id: int, status: str):
    """审核评论:status=ok|hidden|deleted。"""
    ex("UPDATE mu_comment SET status=%s WHERE id=%s", (status, id))
    return {"ok": True, "id": id, "status": status}

# ============ 作品单条编辑(写 work_edit 覆盖层,原 works 不动,可逆) ============
@app.get("/admin/work")
def admin_work_get(id: int):
    """取单件作品的生效值+原始值,供编辑表单回填。"""
    r = q("""SELECT w.work_id, w.title raw_title, w.year raw_year, w.school raw_school, w.medium raw_medium,
                    w.artist_id raw_artist, w.status, w.title_clean, f.cos_key,
                    we.title, we.year, we.school, we.medium, we.artist_id,
                    a.name_cn, a.name_en
             FROM works w JOIN files f ON f.file_id=w.primary_file_id
             LEFT JOIN work_edit we ON we.work_id=w.work_id
             LEFT JOIN artists a ON a.artist_id=COALESCE(we.artist_id,w.artist_id)
             WHERE w.work_id=%s""", (id,), one=True)
    if not r: raise HTTPException(404, "work not found")
    d = dict(r); d["thumb"] = img_url(r["cos_key"], 600)
    return d

@app.post("/admin/work/edit")
def admin_work_edit(id: int, title: str = None, year: str = None, school: str = None,
                    medium: str = None, artist_id: str = None):
    ex("""INSERT INTO work_edit(work_id,title,year,school,medium,artist_id,edited_at)
          VALUES(%s,%s,%s,%s,%s,%s,now())
          ON CONFLICT(work_id) DO UPDATE SET title=EXCLUDED.title,year=EXCLUDED.year,
            school=EXCLUDED.school,medium=EXCLUDED.medium,artist_id=EXCLUDED.artist_id,edited_at=now()""",
       (id, title or None, year or None, school or None, medium or None, artist_id or None))
    return {"ok": True, "id": id}

@app.post("/admin/work/edit/reset")
def admin_work_edit_reset(id: int):
    ex("DELETE FROM work_edit WHERE work_id=%s", (id,))
    return {"ok": True, "id": id}

@app.post("/admin/work/status")
def admin_work_status(id: int, status: str, reason: str = None):
    """人工过闸:status=kept|rejected|archived|pending。"""
    ex("UPDATE works SET status=%s, reject_reason=%s, reviewed_at=now() WHERE work_id=%s",
       (status, reason, id))
    return {"ok": True, "id": id, "status": status}

# ============ 艺术家单条编辑 + 归并纠错 ============
@app.post("/admin/artist/edit")
def admin_artist_edit(artist_id: str, name_cn: str = None, name_en: str = None,
                      born: int = None, death: int = None, east_west: str = None, aha_kg_id: str = None):
    sets, args = [], []
    for col, val in [("name_cn", name_cn), ("name_en", name_en), ("born", born), ("death", death),
                     ("east_west", east_west), ("aha_kg_id", aha_kg_id)]:
        if val is not None and val != "": sets.append(f"{col}=%s"); args.append(val)
    if not sets: return {"ok": False, "msg": "no fields"}
    args.append(artist_id)
    ex(f"UPDATE artists SET {', '.join(sets)} WHERE artist_id=%s", args)
    return {"ok": True, "artist_id": artist_id}

@app.post("/admin/artist/merge")
def admin_artist_merge(frm: str = Query(..., alias="from"), to: str = ""):
    """把 from 归并到 to(canonical=to);纠正漏并。"""
    ex("UPDATE artists SET canonical_artist_id=%s, merge_reason='manual', merge_confidence=1 WHERE artist_id=%s", (to, frm))
    ex("INSERT INTO artist_alias(alias,artist_id) SELECT name_cn,%s FROM artists WHERE artist_id=%s AND name_cn IS NOT NULL ON CONFLICT DO NOTHING", (to, frm))
    return {"ok": True, "from": frm, "to": to}

@app.post("/admin/artist/unmerge")
def admin_artist_unmerge(artist_id: str):
    """拆分:清掉错误归并,该艺术家恢复独立。"""
    ex("UPDATE artists SET canonical_artist_id=NULL, merge_reason='manual_unmerge' WHERE artist_id=%s", (artist_id,))
    return {"ok": True, "artist_id": artist_id}

@app.post("/admin/canon/promote")
def admin_canon_promote(aid: str):
    """把一位活库艺术家「确认制作」为 canon 草稿:建 artists_canon(lore.draft=true,预填实测)+ 把其作品桥到该 canon。
    之后人工补 lore 人文字段即升级为满血策展页。"""
    import re as _r
    d = artist(aid)  # 复用聚合:身份 + 实测 measured + holdings
    if d.get("canon_id"):
        return {"ok": False, "msg": "已是 canon", "canon_id": d["canon_id"]}
    cn_, en_ = d.get("name_cn"), d.get("name_en")
    base = _r.sub(r"[^a-z0-9]", "", (en_ or cn_ or aid).lower()) or _r.sub(r"[^a-z0-9]", "", aid.lower())
    canon_id = "ARTIST." + base[:40]
    if q("SELECT 1 FROM artists_canon WHERE canon_id=%s", (canon_id,), one=True):
        canon_id = canon_id + "-" + _r.sub(r"[^a-z0-9]", "", aid.lower())[-6:]
    m = d.get("measured") or {}; vad = m.get("vad"); wv = m.get("wv") or {}
    affect = ({"v": round(vad["v"]["mean"],3), "a": round(vad["a"]["mean"],3),
               "d": (round(vad["d"]["mean"],3) if vad.get("d") else None), "_measured": True} if vad and vad.get("v") else None)
    wvseed = ({"x": round(wv["x"]["mean"],3), "y": round(wv["y"]["mean"],3), "spread": 0.12,
               "region_id": None, "region_cn": "", "offset": "(待考)", "read": "(待补)", "_measured": True} if wv.get("x") else None)
    lang = {k: round(v["mean"],3) for k, v in (m.get("lang") or {}).items()} or None
    lore = {"draft": True, "verify": {"status": "待制作"}, "source_aid": aid,
            "styles": [s["k"] for s in (d.get("styles") or [])][:6],
            "affect": affect, "wv": wvseed, "lang": lang,
            "titles": [], "teachers": [], "peers": [], "students": [], "subjects": [],
            "trajectory": [], "influence": [], "institutions": []}
    ew = d.get("region") if d.get("region") in ("east", "west") else None
    ex("""INSERT INTO artists_canon(canon_id,cn,en,born,death,region,nationality,lore)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
          ON CONFLICT (canon_id) DO UPDATE SET cn=EXCLUDED.cn,en=EXCLUDED.en,born=EXCLUDED.born,
            death=EXCLUDED.death,region=EXCLUDED.region,nationality=EXCLUDED.nationality,lore=EXCLUDED.lore""",
       (canon_id, cn_, en_, d.get("born"), d.get("death"), ew, d.get("nationality"), json.dumps(lore, ensure_ascii=False)))
    # 桥接:该艺术家全部来源作品挂到新 canon
    ex("UPDATE artists SET aha_kg_id=%s WHERE artist_id=%s OR canonical_artist_id=%s", (canon_id, aid, aid))
    return {"ok": True, "canon_id": canon_id, "cn": cn_, "prefilled": {"affect": bool(affect), "wv": bool(wvseed), "styles": bool(lore["styles"])}}

# ============ 编目:流派归一管理 ============
@app.get("/admin/styles")
def admin_styles():
    """规范流派词表 + 原值→规范映射(带作品数,未归类优先)。"""
    canon = [dict(r) for r in q("SELECT canon_id,name_cn,name_en,sort FROM style_canon ORDER BY sort")]
    rawmap = [dict(r) for r in q("""SELECT sm.raw, sm.canon_id, sm.auto, count(w.work_id) n
        FROM style_map sm LEFT JOIN works w ON w.school=sm.raw AND w.status<>'dup'
        GROUP BY sm.raw,sm.canon_id,sm.auto ORDER BY (sm.canon_id=0) DESC, count(w.work_id) DESC""")]
    return {"canon": canon, "raw_map": rawmap}

@app.post("/admin/style/map")
def admin_style_map(raw: str, canon_id: int):
    """把某原值流派归到规范流派(人工,auto=false 不再被自动覆盖)。"""
    ex("""INSERT INTO style_map(raw,canon_id,auto) VALUES(%s,%s,false)
          ON CONFLICT(raw) DO UPDATE SET canon_id=EXCLUDED.canon_id, auto=false""", (raw, canon_id))
    return {"ok": True, "raw": raw, "canon_id": canon_id}

# ============ 运营:审计日志 + 系统健康 ============
@app.get("/admin/log")
def admin_log(limit: int = 100):
    """后台操作审计:谁在什么时候改了什么。"""
    rows = q("SELECT ts, action, query, actor FROM admin_log ORDER BY ts DESC LIMIT %s", (limit,))
    today = q("SELECT count(*) n FROM admin_log WHERE ts > now()-interval '24 hour'", one=True)["n"]
    by_act = [dict(r) for r in q("SELECT action, count(*) n FROM admin_log GROUP BY action ORDER BY 2 DESC LIMIT 12")]
    return {"recent": [dict(r) for r in rows], "today": today, "by_action": by_act,
            "total": q("SELECT count(*) n FROM admin_log", one=True)["n"]}

@app.post("/admin/reload_thumbs")
def admin_reload_thumbs():
    """gen_thumbs 生成新缩略图后,热加载映射(免重启)。"""
    load_thumb_map()
    return {"ok": True, "thumb_map": len(THUMB_MAP)}

@app.get("/admin/sys")
def admin_sys():
    """系统健康:库大小/表量/治理产物/最近灌库速率。"""
    import shutil
    dbsize = q("SELECT pg_size_pretty(pg_database_size(current_database())) s", one=True)["s"]
    tabs = [dict(r) for r in q("""SELECT relname t, n_live_tup n,
              pg_size_pretty(pg_total_relation_size(relid)) sz
              FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 8""")]
    govern = q("""SELECT (SELECT count(*) FROM works) works,(SELECT count(*) FROM v_ledger) ledger,
                  (SELECT count(*) FROM works WHERE status='pending') pending,
                  (SELECT count(*) FROM works WHERE status='kept') kept,
                  (SELECT count(*) FROM work_edit) edits,
                  (SELECT count(*) FROM artist_alias) aliases""", one=True)
    rate = q("""SELECT count(*) FILTER (WHERE reviewed_at>now()-interval '1 hour') h1,
                count(*) FILTER (WHERE reviewed_at>now()-interval '24 hour') h24
                FROM works WHERE reviewed_at IS NOT NULL""", one=True)
    try:
        du = shutil.disk_usage("/"); disk = {"used_gb": round(du.used/1e9, 1), "total_gb": round(du.total/1e9, 1),
                                             "pct": round(du.used/du.total*100)}
    except Exception:
        disk = None
    return {"db_size": dbsize, "tables": tabs, "govern": dict(govern), "review_rate": dict(rate), "disk": disk}

@app.get("/admin/m/gen")
def m_gen(scope: str = "all", limit: int = 200):
    """生成图库管理(全量,跨用户)。scope=all|rated|unclaimed。"""
    where = "1=1"
    if scope == "rated":
        where = "rating IS NOT NULL"
    elif scope == "unclaimed":
        where = "uid IS NULL"
    rows = q(f"""SELECT g.id, g.uid, g.file, g.prompt, g.meta, g.rating, g.ts,
                        u.nickname, u.email
                 FROM mu_generation g LEFT JOIN mu_user u ON u.uid=g.uid
                 WHERE {where} ORDER BY g.ts DESC LIMIT %s""", (limit,))
    n = q("SELECT count(*) c FROM mu_generation", one=True)["c"]
    nu = q("SELECT count(DISTINCT uid) c FROM mu_generation WHERE uid IS NOT NULL", one=True)["c"]
    items = []
    for r in rows:
        m = r["meta"] or {}
        f = r["file"]
        items.append({"id": r["id"], "uid": r["uid"], "who": r["nickname"] or r["email"] or ("匿名" if not r["uid"] else r["uid"][:10]),
                      "file": "/" + f if not f.startswith("/") else f,
                      "prompt": (r["prompt"] or "")[:160], "style_cn": m.get("style_cn"), "query": m.get("query"),
                      "model": m.get("model_label"), "rating": r["rating"],
                      "ts": r["ts"].isoformat() if r["ts"] else None})
    return {"total": n, "users": nu, "items": items}

@app.post("/admin/gen/rate")
def gen_rate(id: str, rating: int = None):
    ex("UPDATE mu_generation SET rating=%s WHERE id=%s", (rating, id))
    return {"ok": True}

@app.post("/admin/gen/delete")
def gen_delete(id: str):
    r = q("SELECT file FROM mu_generation WHERE id=%s", (id,), one=True)
    if r:
        fp = "/data/pub/p/aha/" + r["file"]
        try:
            if os.path.exists(fp):
                os.remove(fp)
        except Exception:
            pass
    ex("DELETE FROM mu_generation WHERE id=%s", (id,))
    return {"ok": True}

_WVN = {"WV1": "摹写之眼", "WV2": "礼制图式", "WV3": "写意寄情", "WV4": "经验之光", "WV5": "表现外化", "WV6": "形式建构"}
_L7MAP = {"构图与组织": "构图", "透视与空间": "空间", "形状与造型": "造型", "光影与明暗": "光影",
          "色彩系统": "色彩", "笔触与肌理": "笔触", "边缘与节奏": "边缘"}

@app.get("/exhibitions")
def exhibitions():
    """公开展览列表(collections=展览模型,owner_uid 区分官方/用户)。供展厅切换 + 未来用户策展。"""
    rows = q("""SELECT c.collection_id, c.name, c.description, c.owner_uid, c.kind,
                       count(cw.work_id) n,
                       (SELECT f.cos_key FROM collection_works x JOIN works w ON w.work_id=x.work_id
                        JOIN files f ON f.file_id=w.primary_file_id WHERE x.collection_id=c.collection_id LIMIT 1) cover
                FROM collections c LEFT JOIN collection_works cw ON cw.collection_id=c.collection_id
                WHERE c.is_public GROUP BY c.collection_id ORDER BY c.sort, c.collection_id""")
    return {"n": len(rows), "exhibitions": [{"id": r["collection_id"], "name": r["name"],
            "desc": r["description"], "owner": r["owner_uid"], "kind": r["kind"], "count": r["n"],
            "cover": img_url(r["cover"], 400) if r["cover"] else None} for r in rows]}

import time as _time
_EXH_CACHE = {}          # (limit,collection,slim) -> (ts, payload)
_EXH_TTL = 120           # 秒;展出集只在过闸/上展/装裱策展时变,2 分钟缓存够新又省 0.4s 重算

@app.get("/exhibit")
def exhibit(limit: int = 3000, collection: int = None, slim: bool = False):
    _ck = (limit, collection, bool(slim)); _now = _time.time()
    _hit = _EXH_CACHE.get(_ck)
    if _hit and _now - _hit[0] < _EXH_TTL:
        return _hit[1]
    """展出集(供 art.html 消费),输出对齐 gallery_works.json 形态。仅含已 exhibited 且有世界观坐标的。
    slim=1:供 museum 首页瘦身——只回有世界观坐标的作品(首页本就只用这些),且砍掉首页用不到的重字段
    (thumb/voiceover/wvcn/style/medium/subject/frame_*/canon_id),载荷与解析都更小更快。"""
    where = "w.exhibited"; args = []   # 放开门槛:全部 exhibited,有坐标的落世界观平面,没坐标的照常看
    if slim and not collection:
        where = "w.exhibited AND w.vlm ? 'worldview'"   # 首页只上墙有坐标的,服务端先筛掉无坐标的(省 ~30%)
    if collection:
        where = "w.work_id IN (SELECT work_id FROM collection_works WHERE collection_id=%s)"
        args = [collection]
    rows = q(f"""SELECT w.work_id, w.accession_code, w.title, a.name_cn, a.name_en, a.region, w.artist_id, w.year, w.quality,
                        w.vlm, w.style_id, s.name_zh style_zh, f.cos_key, a.aha_kg_id, ac.cn canon_cn
                 FROM works w JOIN artists a ON a.artist_id=w.artist_id JOIN files f ON f.file_id=w.primary_file_id
                 LEFT JOIN styles s ON s.style_id=w.style_id
                 LEFT JOIN artists_canon ac ON ac.canon_id=a.aha_kg_id
                 WHERE {where} ORDER BY w.quality DESC NULLS LAST LIMIT %s""", args + [limit])
    works = []
    for r in rows:
        v = r["vlm"] or {}; wv = v.get("worldview") or {}; af = v.get("affect") or {}; vad = af.get("vad") or {}
        import re as _re2; _m = _re2.search(r"WV[1-6]", str(wv.get("wv") or "")); _wvc = _m.group(0) if _m else None
        L7 = v.get("language7") or {}
        lang = {}
        for full, short in _L7MAP.items():
            o = L7.get(full); lang[short] = (o.get("v") if isinstance(o, dict) else o) if o is not None else None
        item = {"work_id": r["work_id"], "code": r["accession_code"], "file": img_url(r["cos_key"]),
                "title": r["title"] or "无题", "artist": r["canon_cn"] or r["name_cn"] or r["name_en"] or "佚名",
                "aid": r["aha_kg_id"] or r["artist_id"],
                "year": r["year"], "region": r["region"], "wv": _wvc,
                "x": wv.get("x"), "y": wv.get("y"),
                "emo": af.get("primary_anchor"),
                "vad": {"v": vad.get("valence"), "a": vad.get("arousal"), "d": vad.get("dominance")},
                "color": v.get("color"), "lang": lang, "quality": r["quality"]}
        if not slim:
            # 装裱匹配信号:流派 style(规范库 name_zh 优先,回落 vlm.style.流派) + 媒材 medium(清掉「①绘画类型:」前缀)
            _vs = v.get("style") or {}
            style = r["style_zh"] or (_vs.get("流派") if isinstance(_vs, dict) else None)
            medium = v.get("media")
            if isinstance(medium, str):
                medium = _re2.sub(r"^[①-⑳\s]*绘画类型[:：]?\s*", "", medium).strip() or None
            # LLM 逐画装裱策展(frame_curate.py 写入 vlm.frame):前端优先级 人工canonical > 此建议 > 关键词auto
            fr = v.get("frame") or {}
            item.update({"thumb": img_url(r["cos_key"], 600), "canon_id": r["aha_kg_id"],
                         "wvcn": _WVN.get(_wvc), "voiceover": v.get("voiceover"),
                         "style": style, "style_id": r["style_id"],
                         "style_node": style_node_for(r["style_id"]),
                         "medium": medium, "subject": v.get("subject"),
                         "frame_suggest": (fr.get("key") if isinstance(fr, dict) else None),
                         "frame_why": (fr.get("why") if isinstance(fr, dict) else None),
                         "frame_finish": (fr.get("finish") if isinstance(fr, dict) else None),
                         "frame_conf": (fr.get("conf") if isinstance(fr, dict) else None)})
        works.append(item)
    _payload = {"works": works, "n": len(works)}
    _EXH_CACHE[_ck] = (_now, _payload)
    return _payload

@app.get("/foryou")
def foryou(uid: str, limit: int = 24):
    """个性化推荐(reward 内核):供 me.html「为你推荐」与画廊个性化排序。"""
    return aha_profile.foryou(uid, limit=limit)

@app.get("/me/profile")
def me_profile(uid: str):
    """读用户 12 维审美档案(供画廊/详情页做个性化展示)。"""
    return aha_profile.compute_profile(uid)

@app.get("/artist_fit")
def artist_fit(uid: str, id: str):
    """登录用户与某艺术家的契合度:用户 12 维 μ vs 该艺术家真作品聚合向量的 dKG。供 kg-artist 页『与你契合』。"""
    pr = q("SELECT vec FROM mu_profile WHERE uid=%s", (uid,), one=True)
    if not pr or not pr["vec"]:
        return {"ready": False}
    mu = pr["vec"]
    canon_id = id if id.startswith("ARTIST.") else (
        (q("SELECT aha_kg_id FROM artists WHERE artist_id=%s", (id,), one=True) or {}).get("aha_kg_id"))
    if not canon_id:
        return {"ready": False}
    src = [r["artist_id"] for r in q("SELECT artist_id FROM artists WHERE aha_kg_id=%s", (canon_id,))]
    if not src:
        return {"ready": False}
    rows = q("""SELECT w.vlm FROM works w WHERE w.artist_id = ANY(%s) AND w.status='kept' AND w.vlm IS NOT NULL""", (src,))
    vecs = [v for v in (aha_profile.work_vec(r["vlm"]) for r in rows) if v]
    if not vecs:
        return {"ready": False}
    avec = aha_profile.masked_mean(vecs)
    d = aha_profile.dKG(mu, avec)
    aff = round(max(0.0, 1 - d) * 100)
    return {"ready": True, "aff": aff, "dist": round(d, 3), "n": len(vecs)}

@app.get("/work_fit")
def work_fit(uid: str, wid: int):
    """登录用户与单幅画的契合度(用户 μ vs 该画 12 维向量)。供 work.html。"""
    pr = q("SELECT vec FROM mu_profile WHERE uid=%s", (uid,), one=True)
    if not pr or not pr["vec"]:
        return {"ready": False}
    r = q("SELECT vlm FROM works WHERE work_id=%s", (wid,), one=True)
    wvec = aha_profile.work_vec(r["vlm"]) if r else None
    if not wvec:
        return {"ready": False}
    d = aha_profile.dKG(pr["vec"], wvec)
    return {"ready": True, "aff": round(max(0.0, 1 - d) * 100), "dist": round(d, 3)}

@app.get("/taste_atlas")
def taste_atlas(uid: str):
    """登录用户对每位 canon 艺术家的契合度(供星图按口味染色)。canon 向量=其来源艺术家 mu_artist_vec 的加权均值。"""
    pr = q("SELECT vec FROM mu_profile WHERE uid=%s", (uid,), one=True)
    if not pr or not pr["vec"]:
        return {"ready": False, "aff": {}}
    mu = pr["vec"]
    acc = {}
    for r in q("""SELECT a.aha_kg_id cid, m.vec, m.n FROM mu_artist_vec m
                  JOIN artists a ON a.artist_id=m.artist_id WHERE a.aha_kg_id IS NOT NULL"""):
        acc.setdefault(r["cid"], []).append((r["vec"], r["n"] or 1))
    out = {}
    for cid, lst in acc.items():
        cvec = aha_profile.masked_mean([v for v, n in lst], [n for v, n in lst])
        out[cid] = round(max(0.0, 1 - aha_profile.dKG(mu, cvec)) * 100)
    return {"ready": True, "aff": out, "n": len(out)}

import re as _re_canon
def _era_from_lore(lore, born):
    """有生年用生年;否则从轨迹/卒年文字估个大概数值年代,era_disp 给原文显示。"""
    if born is not None:
        return born, None
    for pt in (lore.get("trajectory") or []):
        s = pt.get("year")
        if not s: continue
        m = _re_canon.search(r'(\d+)\s*世纪\s*(初|前|中|末|后)?', str(s))
        if m:
            c = int(m.group(1)); pos = {'初':15,'前':25,'中':50,'末':85,'后':75}.get(m.group(2), 50)
            return (c-1)*100+pos, str(s)
        m = _re_canon.search(r'(\d+)\s*[–\-~]?\s*(\d+)?\s*[Cc](?![a-z])', str(s))
        if m:
            c1 = int(m.group(1)); c2 = int(m.group(2)) if m.group(2) else c1
            return int(((c1+c2)/2-1)*100+50), str(s)
        m = _re_canon.search(r'(\d{3,4})', str(s))
        if m: return int(m.group(1)), str(s)
    return None, None

@app.get("/artists_canon")
def artists_canon():
    cnts = {r["aha_kg_id"]: r["n"] for r in q(
        "SELECT a.aha_kg_id, count(*) n FROM works w JOIN artists a ON a.artist_id=w.artist_id "
        "WHERE w.status='kept' AND a.aha_kg_id IS NOT NULL GROUP BY a.aha_kg_id")}
    arts = []
    for r in q("SELECT canon_id, cn, en, region, born, death, lore FROM artists_canon"):
        L = r["lore"] or {}; wv = L.get("wv") or {}; styles = L.get("styles") or []
        era, era_disp = _era_from_lore(L, r["born"])
        primary = (styles[0] if styles else None) or wv.get("region_cn") or "—"
        arts.append({"id": r["canon_id"], "cn": r["cn"], "en": r["en"], "region": r["region"],
                     "born": r["born"], "death": r["death"], "n": cnts.get(r["canon_id"], 0),
                     "wx": wv.get("x"), "wy": wv.get("y"), "wv": wv.get("region_id"),
                     "era": era, "era_disp": era_disp, "primary": primary,
                     "portrait": L.get("portrait"), "portrait_src": L.get("portrait_src"),
                     "authored": not L.get("draft"), "draft": bool(L.get("draft"))})
    arts.sort(key=lambda a: (a["era"] if a["era"] is not None else 9999, a["cn"] or ""))
    return {"n": len(arts), "artists": arts}

@app.get("/measured_atlas")
def measured_atlas(min_n: int = 3):
    """每位 canon 艺术家由真作品 VLM 世界观坐标聚合的实测重心(供星图画'策展→实测'漂移)。"""
    rows = q("""SELECT a.aha_kg_id id,
                       avg((w.vlm->'worldview'->>'x')::float) x,
                       avg((w.vlm->'worldview'->>'y')::float) y, count(*) n
                FROM works w JOIN artists a ON a.artist_id=w.artist_id
                WHERE a.aha_kg_id IS NOT NULL AND w.status='kept'
                      AND w.vlm->'worldview'->>'x' IS NOT NULL
                GROUP BY a.aha_kg_id HAVING count(*) >= %s""", (min_n,))
    return {"artists": {r["id"]: {"x": round(r["x"], 3), "y": round(r["y"], 3), "n": r["n"]} for r in rows}}

@app.get("/artist")
def artist(id: str):
    # 解析 canon:ARTIST.* 直接;来源 id 则查其 aha_kg_id
    canon_id = id if id.startswith("ARTIST.") else None
    if not canon_id:
        r = q("SELECT aha_kg_id FROM artists WHERE artist_id=%s", (id,), one=True)
        if r and r["aha_kg_id"]: canon_id = r["aha_kg_id"]
    canon = q("SELECT * FROM artists_canon WHERE canon_id=%s", (canon_id,), one=True) if canon_id else None
    # 聚合范围:canon 下所有来源艺术家;否则单个来源
    if canon_id:
        src = [r["artist_id"] for r in q("SELECT artist_id FROM artists WHERE aha_kg_id=%s", (canon_id,))]
        if not src: src = [id]
    else:
        # 非 canon:按归并 canonical 聚合该艺术家全部来源(跨 nbfox/wikiart/yh),与馆藏总数对齐
        cr = q("SELECT COALESCE(canonical_artist_id, artist_id) c FROM artists WHERE artist_id=%s", (id,), one=True)
        key = cr["c"] if cr else id
        src = [r["artist_id"] for r in q("SELECT artist_id FROM artists WHERE artist_id=%s OR canonical_artist_id=%s", (key, key))]
        if not src: src = [id]
    a = q("SELECT artist_id,name_cn,name_en,born,death,region,nationality FROM artists WHERE artist_id=%s", (id if not canon_id else src[0],), one=True) or {}
    rows = q("""SELECT w.work_id,w.accession_code,w.title,w.quality,s.name_zh style_zh,w.vlm,f.cos_key
                FROM works w JOIN files f ON f.file_id=w.primary_file_id LEFT JOIN styles s ON s.style_id=w.style_id
                WHERE w.artist_id = ANY(%s) AND w.status='kept' AND w.vlm IS NOT NULL
                ORDER BY w.quality DESC NULLS LAST LIMIT 160""", (src,))
    import re as _r
    def _numv(o):  # language7 项稳健取 0-1 数值
        if isinstance(o, (int, float)): return float(o)
        if isinstance(o, dict) and isinstance(o.get("v"), (int, float)): return float(o["v"])
        if isinstance(o, str):
            m = _r.search(r"(\d*\.?\d+)", o)
            return float(m.group(1)) if m else None
        return None
    works = []; stylec = {}; vs = []; as_ = []; ds_ = []; wvpts = []; vadpts = []
    langacc = {s: [] for s in _L7MAP.values()}  # 七大构成实测:每轴收集各画值
    for r in rows:
        v = r["vlm"] or {}; af = v.get("affect") or {}; vad = af.get("vad") or {}; wv = v.get("worldview") or {}
        L7 = v.get("language7") or {}
        if r["style_zh"]: stylec[r["style_zh"]] = stylec.get(r["style_zh"], 0) + 1
        if vad.get("valence") is not None:
            vs.append(float(vad["valence"])); as_.append(float(vad.get("arousal") or 0))
            if vad.get("dominance") is not None: ds_.append(float(vad["dominance"]))
            vadpts.append({"id": r["work_id"], "title": r["title"] or "无题",
                           "v": round(float(vad["valence"]), 3), "a": round(float(vad.get("arousal") or 0), 3)})
        for full, short in _L7MAP.items():
            fv = _numv(L7.get(full))
            if fv is not None: langacc[short].append(fv)
        item = {"id": r["work_id"], "code": r["accession_code"], "title": r["title"] or "无题", "thumb": img_url(r["cos_key"], 300),
                "anchor": af.get("primary_anchor"), "style": r["style_zh"], "quality": r["quality"]}
        if wv.get("x") is not None:
            mw = _r.search(r"WV[1-6]", str(wv.get("wv") or ""))
            item["wx"] = wv.get("x"); item["wy"] = wv.get("y"); item["wv"] = mw.group(0) if mw else None
            wvpts.append(item)
        item["v"] = vad.get("valence"); item["a"] = vad.get("arousal")
        works.append(item)
    tot = q("SELECT count(*) c FROM works WHERE artist_id = ANY(%s) AND status='kept'", (src,), one=True)["c"]
    # 全部馆藏(非 dup):深页显示真实持有量,不止过闸的 kept(C)
    n_holdings = q("SELECT count(*) c FROM works WHERE artist_id = ANY(%s) AND status<>'dup'", (src,), one=True)["c"]
    holdings = [{"id": r["work_id"], "title": r["title"] or "无题", "thumb": img_url(r["cos_key"], 300),
                 "quality": r["quality"]} for r in q(
        """SELECT w.work_id, w.title, w.quality, f.cos_key
           FROM works w JOIN files f ON f.file_id=w.primary_file_id
           WHERE w.artist_id = ANY(%s) AND w.status<>'dup'
           ORDER BY w.quality DESC NULLS LAST LIMIT 120""", (src,))]
    cen = {"v": round(sum(vs)/len(vs), 3), "a": round(sum(as_)/len(as_), 3)} if vs else None
    styles = [{"k": k, "n": n} for k, n in sorted(stylec.items(), key=lambda x: -x[1])]
    # 🔬 实测聚合(自下而上:艺术家向量 = 真作品 VLM 向量的聚合)
    def _stat(xs):
        if not xs: return None
        m = sum(xs)/len(xs); sd = (sum((x-m)**2 for x in xs)/len(xs))**0.5
        return {"mean": round(m, 3), "sd": round(sd, 3), "n": len(xs)}
    lang_meas = {k: _stat(xs) for k, xs in langacc.items() if xs}
    vad_meas = None
    if vs:
        vad_meas = {"v": _stat(vs), "a": _stat(as_), "d": (_stat(ds_) if ds_ else None)}
    # 世界观实测:真作品 VLM 世界观坐标的重心+离散+点云(refill_worldview 补全后可用)
    wv_meas = None
    wxs = [p["wx"] for p in wvpts if p.get("wx") is not None]
    wys = [p["wy"] for p in wvpts if p.get("wy") is not None]
    if wxs:
        from collections import Counter as _C
        regc = _C(p.get("wv") for p in wvpts if p.get("wv"))
        wv_meas = {"x": _stat(wxs), "y": _stat(wys), "n": len(wxs),
                   "region": (regc.most_common(1)[0][0] if regc else None),
                   "points": [{"x": round(p["wx"], 3), "y": round(p["wy"], 3), "id": p["id"]} for p in wvpts[:200]]}
    measured = {"n_works": tot, "n_lang": max((len(x) for x in langacc.values()), default=0),
                "n_vad": len(vs), "lang": lang_meas, "vad": vad_meas, "wv": wv_meas,
                "vad_points": vadpts[:200],
                "note": "实测=该艺术家已入库真作品经 VLM 逐张量后的聚合(均值±标准差);世界观坐标=真作品 VLM 逐张读图(refill_worldview)"}
    lore = canon["lore"] if canon else None
    return {"id": canon_id or a.get("artist_id") or id, "canon_id": canon_id,
            "name_cn": (canon["cn"] if canon else a.get("name_cn")),
            "name_en": (canon["en"] if canon else a.get("name_en")),
            "born": (canon["born"] if canon else a.get("born")),
            "death": (canon["death"] if canon else a.get("death")),
            "region": (canon["region"] if canon else a.get("region")),
            "nationality": (canon["nationality"] if canon else a.get("nationality")),
            "curated": bool(canon), "draft": bool((lore or {}).get("draft")), "lore": lore,
            "n_kept": tot, "n_holdings": n_holdings, "holdings": holdings,
            "n_sources": len(src), "vad_centroid": cen, "measured": measured,
            "styles": styles, "wv_points": wvpts, "works": works}

@app.get("/work/{wid}")
def work(wid: str):
    work_id = _resolve_wid(wid)
    if work_id is None: raise HTTPException(404, "work not found")
    r = q("""SELECT w.work_id, w.accession_code, w.title, w.year, w.school, s.name_zh style_zh, w.medium, w.w_cm, w.h_cm,
                    w.status, w.quality, w.exhibited, w.vlm, w.source_batch,
                    a.artist_id, a.name_cn, a.name_en, a.born, a.death, a.region, a.aha_kg_id,
                    f.cos_key, f.width, f.height
             FROM works w JOIN artists a ON a.artist_id=w.artist_id
             JOIN files f ON f.file_id=w.primary_file_id
             LEFT JOIN styles s ON s.style_id=w.style_id WHERE w.work_id=%s""", (work_id,), one=True)
    if not r: raise HTTPException(404, "work not found")
    # canon 显示名优先(对齐 kg-artist 页)
    canon_cn = None
    if r["aha_kg_id"]:
        c = q("SELECT cn FROM artists_canon WHERE canon_id=%s", (r["aha_kg_id"],), one=True)
        canon_cn = c["cn"] if c else None
    return {"id": r["work_id"], "code": r["accession_code"], "title": r["title"], "year": r["year"],
            "school": r["style_zh"] or r["school"],
            "medium": r["medium"], "w_cm": r["w_cm"], "h_cm": r["h_cm"],
            "status": r["status"], "quality": r["quality"], "source": r["source_batch"],
            "exhibited": bool(r["exhibited"]), "file": img_url(r["cos_key"]),
            "artist": {"name_cn": canon_cn or r["name_cn"], "name_en": r["name_en"],
                       "born": r["born"], "death": r["death"], "region": r["region"],
                       "canon_id": r["aha_kg_id"], "artist_id": r["artist_id"]},
            "image": {"full": img_url(r["cos_key"]), "thumb": img_url(r["cos_key"], 800),
                      "w": r["width"], "h": r["height"]},
            "vlm": r["vlm"]}

@app.get("/related/{wid}")
def related(wid: str, limit: int = 8):
    """单幅画的相关作品:同一画家 → 同一情绪锚点 → 同一风格,去重。"""
    work_id = _resolve_wid(wid)
    if work_id is None:
        raise HTTPException(404, "work not found")
    base = q("SELECT artist_id, style_id, vlm->'affect'->>'primary_anchor' anchor "
             "FROM works WHERE work_id=%s", (work_id,), one=True)
    if not base:
        raise HTTPException(404, "work not found")
    seen = {work_id}
    out = []
    SEL = ("SELECT w.work_id, w.accession_code, w.title, a.name_cn, a.name_en, f.cos_key, %s rel "
           "FROM works w JOIN artists a ON a.artist_id=w.artist_id "
           "JOIN files f ON f.file_id=w.primary_file_id "
           "WHERE w.status='kept' AND w.work_id<>%s AND {cond} "
           "ORDER BY w.quality DESC NULLS LAST LIMIT %s")
    def add(rel, cond, val, n):
        for r in q(SEL.format(cond=cond), (rel, work_id, val, n)):
            if r["work_id"] in seen:
                continue
            seen.add(r["work_id"])
            out.append({"id": r["work_id"], "code": r["accession_code"], "title": r["title"],
                        "artist": r["name_cn"] or r["name_en"],
                        "thumb": img_url(r["cos_key"], 400), "rel": r["rel"]})
    if base["artist_id"]:
        add("同一画家", "w.artist_id=%s", base["artist_id"], 4)
    if base["anchor"]:
        add("同一情绪", "w.vlm->'affect'->>'primary_anchor'=%s", base["anchor"], 6)
    if base["style_id"]:
        add("同一风格", "w.style_id=%s", base["style_id"], 6)
    return {"items": out[:limit]}

# ============ 生成数据区(InfMonkeys,独立 zone,不碰真迹) ============
@app.get("/gen")
def gen(workflow: str = None, model: str = None, color: str = None,
        kw: str = Query(None, alias="q"), qstatus: str = None, sort: str = None,
        date_from: str = None, date_to: str = None, limit: int = 30, offset: int = 0):
    """生成区浏览+筛选:artist 平台 + 造物云艺术数据。"""
    where = ["gf.role='output'", "(r.source IS NULL OR (r.source='zaowuyun_team' AND gf.category LIKE 'art/%%'))"]
    args = []
    if workflow: where.append("r.workflow_name=%s"); args.append(workflow)
    if model: where.append("r.params->>'model'=%s"); args.append(model)
    if color: where.append("gf.hue=%s"); args.append(color)
    if qstatus: where.append("gf.q_status=%s"); args.append(qstatus)
    if kw: where.append("(r.input_prompt ILIKE %s OR r.final_prompt ILIKE %s)"); args += ['%'+kw+'%', '%'+kw+'%']
    if date_from: where.append("r.start_time >= %s"); args.append(date_from)
    if date_to: where.append("r.start_time < (%s::date + 1)"); args.append(date_to)
    wsql = " AND ".join(where)
    order = "gf.quality DESC NULLS LAST" if sort == "quality" else "r.start_time DESC NULLS LAST, gf.gen_file_id"
    rows = q(f"""SELECT r.instance_id, r.workflow_id, r.workflow_name, r.input_prompt, r.final_prompt,
                        r.system_prompt, r.seed, r.params, r.status, r.input_images,
                        extract(epoch from r.start_time) st, extract(epoch from r.end_time) et,
                        r.raw, r.source as r_source,
                        gf.gen_file_id, gf.cos_key, gf.src_url, gf.sha256, gf.phash,
                        gf.width, gf.height, gf.bytes, gf.fmt,
                        gf.ave_rgb, gf.hue, gf.sharpness,
                        gf.q_status, gf.quality, gf.vlm, gf.category, gf.src_id, gf.display_name
                 FROM gen_run r JOIN gen_file gf ON gf.instance_id=r.instance_id
                 WHERE {wsql}
                 ORDER BY {order}
                 OFFSET %s LIMIT %s""", args + [offset, limit])
    items = [{"id": r["instance_id"], "workflow_id": r["workflow_id"], "workflow": r["workflow_name"],
              "input_prompt": r["input_prompt"], "final_prompt": r["final_prompt"],
              "system_prompt": r["system_prompt"], "params": r["params"] or {},
              "seed": r["seed"], "status": r["status"],
              "input_images": r["input_images"] or [],
              "time": int(r["st"]*1000) if r["st"] else None,
              "end_time": int(r["et"]*1000) if r["et"] else None,
              "duration": int(r["et"] - r["st"]) if r["st"] and r["et"] else None,
              "raw": r["raw"], "source": r["r_source"],
              "gen_file_id": r["gen_file_id"],
              "cos_key": r["cos_key"], "src_url": r["src_url"],
              "sha256": r["sha256"], "phash": r["phash"],
              "ave_rgb": r["ave_rgb"], "hue": r["hue"], "sharpness": r["sharpness"],
              "q_status": r["q_status"], "quality": r["quality"],
              "vlm": r["vlm"], "category": r["category"],
              "src_id": r["src_id"], "display_name": r["display_name"],
              "image": img_url(r["cos_key"]), "thumb": img_url(r["cos_key"], 700),
              "w": r["width"], "h": r["height"], "size": r["bytes"], "fmt": r["fmt"]} for r in rows]
    matched = q(f"SELECT count(*) n FROM gen_run r JOIN gen_file gf ON gf.instance_id=r.instance_id WHERE {wsql}", args, one=True)["n"]
    tot = q("SELECT count(*) n FROM gen_file gf JOIN gen_run r ON r.instance_id=gf.instance_id WHERE gf.role='output' AND (r.source IS NULL OR (r.source='zaowuyun_team' AND gf.category LIKE 'art/%%'))", one=True)["n"]
    return {"items": items, "matched": matched, "total_runs": tot}

@app.get("/gen/facets")
def gen_facets():
    """筛选项:工作流/模型/色彩/分类 各自的计数。artist 平台 + 造物云艺术数据。"""
    src = "(gr.source IS NULL OR (gr.source='zaowuyun_team' AND gf.category LIKE 'art/%%'))"
    wf = q(f"SELECT gr.workflow_name k, count(*) n FROM gen_run gr JOIN gen_file gf ON gf.instance_id=gr.instance_id AND gf.role='output' WHERE {src} GROUP BY 1 ORDER BY 2 DESC")
    md = q(f"SELECT coalesce(gr.params->>'model','?') k, count(*) n FROM gen_run gr JOIN gen_file gf ON gf.instance_id=gr.instance_id AND gf.role='output' WHERE {src} GROUP BY 1 ORDER BY 2 DESC")
    co = q(f"SELECT gf.hue k, gf.count n, gf.rgb FROM (SELECT hue, count(*) count, mode() WITHIN GROUP (ORDER BY ave_rgb) rgb FROM gen_file gf JOIN gen_run gr ON gr.instance_id=gf.instance_id WHERE gf.role='output' AND gf.hue IS NOT NULL AND {src} GROUP BY hue) gf ORDER BY n DESC")
    qs = q(f"SELECT gf.q_status k, count(*) n FROM gen_file gf JOIN gen_run gr ON gr.instance_id=gf.instance_id WHERE gf.role='output' AND {src} GROUP BY 1 ORDER BY 2 DESC")
    cats = q(f"SELECT split_part(gf.category,'/',1) k, count(*) n FROM gen_file gf JOIN gen_run gr ON gr.instance_id=gf.instance_id WHERE gf.role='output' AND {src} AND gf.category IS NOT NULL GROUP BY 1 ORDER BY 2 DESC")
    return {"workflow": [{"k": r["k"], "n": r["n"]} for r in wf],
            "model": [{"k": r["k"], "n": r["n"]} for r in md],
            "color": [{"k": r["k"], "n": r["n"], "rgb": r["rgb"]} for r in co],
            "qstatus": [{"k": r["k"], "n": r["n"]} for r in qs],
            "categories": [{"k": r["k"], "n": r["n"]} for r in cats]}

# ---------- 人工打分(多人评分 + 评估排行) ----------
@app.post("/gen/rate")
def gen_rate(cos_key: str, rater: str, score: int, comment: str = None):
    rater = (rater or "").strip()[:40]
    comment = (comment or "").strip()[:1000] or None
    if not rater or score < 1 or score > 5: raise HTTPException(400, "bad rater/score")
    inst = q("SELECT instance_id FROM gen_file WHERE cos_key=%s", (cos_key,), one=True)
    if not inst: raise HTTPException(404, "image not found")
    ex("""INSERT INTO gen_rating(cos_key,instance_id,rater,score,comment) VALUES(%s,%s,%s,%s,%s)
          ON CONFLICT(cos_key,rater) DO UPDATE SET score=EXCLUDED.score, comment=EXCLUDED.comment, created_at=now()""",
       (cos_key, inst["instance_id"], rater, score, comment))
    agg = q("SELECT round(avg(score)::numeric,2) avg, count(*) n FROM gen_rating WHERE cos_key=%s", (cos_key,), one=True)
    return {"ok": True, "avg": float(agg["avg"]), "n": agg["n"]}

@app.get("/gen/rate/next")
def gen_rate_next(rater: str, workflow: str = None):
    """给该评分人取一张还没评过的生成图(优先没人评/评的人少的,扩大覆盖)。artist 平台 + 造物云艺术数据。"""
    where = ["gf.role='output'", "gf.q_status<>'rejected'",
             "(r.source IS NULL OR (r.source='zaowuyun_team' AND gf.category LIKE 'art/%%'))"]
    args = [rater]
    if workflow: where.append("r.workflow_name=%s"); args.append(workflow)
    wsql = " AND ".join(where)
    row = q(f"""SELECT gf.cos_key, r.instance_id, r.workflow_name, r.input_prompt, r.final_prompt,
                       extract(epoch from r.start_time) st, gf.hue, gf.ave_rgb,
                       (SELECT count(*) FROM gen_rating gr WHERE gr.cos_key=gf.cos_key) votes
                FROM gen_file gf JOIN gen_run r ON r.instance_id=gf.instance_id
                WHERE {wsql} AND NOT EXISTS(SELECT 1 FROM gen_rating gr WHERE gr.cos_key=gf.cos_key AND gr.rater=%s)
                ORDER BY votes ASC, random() LIMIT 1""", args, one=True)
    if not row: return {"done": True}
    mine = q("SELECT count(*) n FROM gen_rating WHERE rater=%s", (rater,), one=True)["n"]
    return {"done": False, "mine": mine,
            "item": {"cos_key": row["cos_key"], "id": row["instance_id"], "workflow": row["workflow_name"],
                     "input_prompt": row["input_prompt"], "final_prompt": row["final_prompt"],
                     "time": int(row["st"]*1000) if row["st"] else None, "votes": row["votes"],
                     "image": img_url(row["cos_key"]), "thumb": img_url(row["cos_key"], 900)}}

@app.get("/gen/leaderboard")
def gen_leaderboard(limit: int = 30):
    """排行榜。仅 artist.infmonkeys.com 数据。"""
    tot = q("SELECT count(*) n, count(DISTINCT rater) r, count(DISTINCT cos_key) k FROM gen_rating", one=True)
    src = "(r.source IS NULL OR (r.source='zaowuyun_team' AND gf.category LIKE 'art/%%'))"
    top = q(f"""SELECT gr.cos_key, round(avg(gr.score)::numeric,2) avg, count(*) n,
                      gf.quality vlm_q, gf.vlm->>'category' vlm_cat
               FROM gen_rating gr JOIN gen_file gf ON gf.cos_key=gr.cos_key
               JOIN gen_run r ON r.instance_id=gf.instance_id
               WHERE {src}
               GROUP BY gr.cos_key, gf.quality, gf.vlm->>'category'
               HAVING count(*)>=1 ORDER BY avg DESC, n DESC LIMIT %s""", (limit,))
    raters = q(f"""SELECT gr.rater, count(*) n, round(avg(gr.score)::numeric,2) avg
                 FROM gen_rating gr JOIN gen_file gf ON gf.cos_key=gr.cos_key
                 JOIN gen_run r ON r.instance_id=gf.instance_id
                 WHERE {src} GROUP BY 1 ORDER BY 2 DESC""")
    corr = q(f"""SELECT corr(h.avg, gf.quality) c, count(*) n FROM
                  (SELECT cos_key, avg(score) avg FROM gen_rating GROUP BY 1) h
                  JOIN gen_file gf ON gf.cos_key=h.cos_key
                  JOIN gen_run r ON r.instance_id=gf.instance_id
                  WHERE gf.quality IS NOT NULL AND {src}""", one=True)
    fb = q("""SELECT gr.rater, gr.score, gr.comment, gr.cos_key, extract(epoch from gr.created_at) ts
              FROM gen_rating gr WHERE gr.comment IS NOT NULL AND gr.comment<>''
              ORDER BY gr.created_at DESC LIMIT 60""")
    nfb = q("SELECT count(*) n FROM gen_rating WHERE comment IS NOT NULL AND comment<>''", one=True)["n"]
    lbnames = _rater_names([r["rater"] for r in raters] + [f["rater"] for f in fb])
    return {"totals": {"ratings": tot["n"], "raters": tot["r"], "rated_images": tot["k"], "comments": nfb},
            "top": [{"cos_key": t["cos_key"], "image": img_url(t["cos_key"], 500), "avg": float(t["avg"]),
                     "n": t["n"], "vlm_quality": t["vlm_q"], "vlm_category": t["vlm_cat"]} for t in top],
            "raters": [{"rater": r["rater"], "name": lbnames.get(r["rater"]) or r["rater"],
                        "n": r["n"], "avg": float(r["avg"])} for r in raters],
            "feedback": [{"rater": lbnames.get(f["rater"]) or f["rater"], "score": f["score"], "comment": f["comment"],
                          "thumb": img_url(f["cos_key"], 200), "time": int(f["ts"]*1000) if f["ts"] else None} for f in fb],
            "human_vs_vlm_corr": (round(float(corr["c"]), 3) if corr["c"] is not None else None), "corr_n": corr["n"]}

# ---------- 美学竞技场:AB 对决 + Bradley-Terry ----------
# 资格口径与 /gen/rate/next 完全一致(artist 平台 + 造物云油画)。'art/%%' 两个通配等价单个,无参/带参都安全。
ARENA_SCOPE = ("gf.role='output' AND gf.q_status<>'rejected' "
               "AND (r.source IS NULL OR (r.source='zaowuyun_team' AND gf.category LIKE 'art/%%'))")

BT_REG = 2.0   # 收缩先验:每个对象额外打 reg 场"对均值(强度1)的虚拟赛",胜负各半 → 没比够的图分数往 1000 收,不出极端值

def bt_scores(pairs, iters=80, reg=BT_REG):
    """Bradley-Terry 极大似然(MM 不动点迭代)+ 收缩先验。pairs: [(winner_key, loser_key, weight)],tie 拆两条 0.5。
       reg>0 时给每个对象加 reg 场对"强度1锚点"的虚拟平局(reg/2 胜+reg/2 负),把稀疏对象往均值(1000)收。
       返回 {key: elo 风格分}(几何均值归一后 1000 + 400·log10(p))。"""
    import math
    keys = set()
    for a, b, _ in pairs:
        keys.add(a); keys.add(b)
    if not keys: return {}
    idx = {k: i for i, k in enumerate(keys)}
    n = len(idx)
    W = [0.0] * n                       # 各对象胜场(含 tie 0.5)
    tot = {}                            # 无向对局总数 (min,max)->次数
    for a, b, w in pairs:
        i, j = idx[a], idx[b]
        W[i] += w
        key = (i, j) if i < j else (j, i)
        tot[key] = tot.get(key, 0) + w  # 用权重累计(tie 两条各 0.5 → 该对 +1 场)
    half = reg / 2.0
    p = [1.0] * n
    for _ in range(iters):
        denom = [0.0] * n
        for (i, j), c in tot.items():
            s = p[i] + p[j]
            if s <= 0: continue
            denom[i] += c / s; denom[j] += c / s
        if reg > 0:
            for i in range(n):
                denom[i] += reg / (p[i] + 1.0)        # reg 场 vs 固定强度1锚点
        np_ = [((W[i] + half) / denom[i]) if denom[i] > 0 else p[i] for i in range(n)]
        pos = [x for x in np_ if x > 0]
        if pos:
            gm = math.exp(sum(math.log(x) for x in pos) / len(pos))
            if gm > 0: np_ = [x / gm for x in np_]
        p = np_
    return {k: (1000 + 400 * math.log10(max(p[i], 1e-9))) for k, i in idx.items()}

def bt_ci(pairs, B=120, iters=40, reg=BT_REG):
    """bootstrap 置信区间:重采样对决 B 次各算一遍 BT,取每张图的 5%/95% 分位。
       返回 (ci, base):ci={key:(lo,hi)},base=点估计(全量)。供"按置信下界排序 + 误差棒"。"""
    import random
    base = bt_scores(pairs, reg=reg)
    keys = list(base.keys())
    L = len(pairs)
    if L == 0 or not keys:
        return {}, base
    samples = {k: [] for k in keys}
    for _ in range(B):
        rs = [pairs[random.randrange(L)] for _ in range(L)]   # 有放回重采样
        sc = bt_scores(rs, iters=iters, reg=reg)
        for k in keys:
            if k in sc: samples[k].append(sc[k])
    ci = {}
    for k in keys:
        s = sorted(samples[k])
        if len(s) >= 10:
            lo = s[int(0.05 * (len(s) - 1))]; hi = s[int(0.95 * (len(s) - 1))]
        else:
            lo = base[k] - 400; hi = base[k] + 400            # 重采样里几乎没出现 → 极不确定,给宽区间
        ci[k] = (lo, hi)
    return ci, base

def _pearson(xs, ys):
    n = len(xs)
    if n < 3: return None
    mx = sum(xs) / n; my = sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs); sy = sum((y - my) ** 2 for y in ys)
    if sx <= 0 or sy <= 0: return None
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    return cov / (sx ** 0.5 * sy ** 0.5)

def _rater_names(uids):
    """评审标识(登录用户=uid,匿名=aha_uid,老数据=手填名)→ 展示昵称。
       命中 mu_user 用昵称;否则原样返回(老手填名),匿名 uid 前端再美化。"""
    us = [u for u in set(uids) if u]
    if not us: return {}
    out = {}
    try:
        for x in q("SELECT uid, nickname FROM mu_user WHERE uid = ANY(%s)", (us,)):
            if x["nickname"]: out[x["uid"]] = x["nickname"]
    except Exception:
        pass
    return out

@app.get("/gen/battle/next")
def gen_battle_next(rater: str, session: str = None):
    """给评审配一对生成图(低曝光优先,扩大覆盖;避开该评审已比过的同一对)。"""
    rater = (rater or "").strip()[:40]
    if not rater: raise HTTPException(400, "no rater")
    cands = q(f"""WITH exp AS (
                    SELECT k, count(*) c FROM (
                      SELECT left_key k FROM gen_battle UNION ALL SELECT right_key FROM gen_battle) t GROUP BY k)
                  SELECT gf.cos_key key, gf.instance_id inst, r.workflow_name wf, gf.category cat,
                         COALESCE(r.final_prompt, r.input_prompt) prompt, COALESCE(e.c, 0) ex
                  FROM gen_file gf JOIN gen_run r ON r.instance_id=gf.instance_id
                  LEFT JOIN exp e ON e.k=gf.cos_key
                  WHERE {ARENA_SCOPE}
                  ORDER BY COALESCE(e.c, 0) ASC, random() LIMIT 60""")
    if not cands or len(cands) < 2:
        return {"done": True}
    import random
    a = cands[0]
    # 该评审比过的对(任一方向),避免重复配对
    done = q("SELECT left_key, right_key FROM gen_battle WHERE rater=%s", (rater,))
    seen = set()
    for d in done:
        seen.add((d["left_key"], d["right_key"])); seen.add((d["right_key"], d["left_key"]))
    rest = [c for c in cands[1:] if (a["key"], c["key"]) not in seen] or cands[1:]
    # 同题材优先(~70%):A 有 category 且候选里有同类时,多数情况配同题材,比的才是质量不是题材偏好;
    # 余下跨题材保持全局排名连通。category 缺失(infmonkeys)则自由配。
    b = None
    if a.get("cat"):
        same = [c for c in rest if c.get("cat") == a["cat"]]
        if same and random.random() < 0.7:
            b = same[0]
    if b is None:
        b = rest[0]
    mine = q("SELECT count(*) n FROM gen_battle WHERE rater=%s", (rater,), one=True)["n"]
    def pack(x):
        return {"cos_key": x["key"], "workflow": x["wf"], "prompt": x["prompt"],
                "category": (x.get("cat") or "").split("/")[-1] or None,
                "image": img_url(x["key"]), "thumb": img_url(x["key"], 900)}
    return {"done": False, "mine": mine, "a": pack(a), "b": pack(b)}

AXES = ("overall", "real", "creative")   # 综合 / 去AI感(更真实) / 创意

@app.post("/gen/battle")
def gen_battle_post(rater: str, left_key: str, right_key: str, winner: str, session: str = None, axis: str = "overall"):
    rater = (rater or "").strip()[:40]
    if axis not in AXES: axis = "overall"
    if not rater or winner not in ("left", "right", "tie", "both_bad"):
        raise HTTPException(400, "bad rater/winner")
    li = q("SELECT instance_id FROM gen_file WHERE cos_key=%s", (left_key,), one=True)
    ri = q("SELECT instance_id FROM gen_file WHERE cos_key=%s", (right_key,), one=True)
    if not li or not ri: raise HTTPException(404, "image not found")
    ex("""INSERT INTO gen_battle(rater,left_key,right_key,left_inst,right_inst,winner,session,axis)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
       (rater, left_key, right_key, li["instance_id"], ri["instance_id"], winner, session, axis))
    mine = q("SELECT count(*) n FROM gen_battle WHERE rater=%s", (rater,), one=True)["n"]
    # 即时反馈:你选的那张,在大家眼里是否也更强(比两张的历史胜率)
    leads = None
    if winner in ("left", "right"):
        chosen, other = (left_key, right_key) if winner == "left" else (right_key, left_key)
        def winrate(k):
            r = q("""SELECT count(*) FILTER(WHERE (left_key=%s AND winner='left') OR (right_key=%s AND winner='right')) w,
                            count(*) FILTER(WHERE winner IN ('left','right') AND (left_key=%s OR right_key=%s)) t
                     FROM gen_battle WHERE left_key=%s OR right_key=%s""", (k, k, k, k, k, k), one=True)
            return (r["w"] / r["t"], r["t"]) if r["t"] else (None, 0)
        wc, tc = winrate(chosen); wo, to = winrate(other)
        if tc >= 2 and to >= 2 and wc is not None and wo is not None:
            leads = wc >= wo
    return {"ok": True, "mine": mine, "leads": leads}

@app.get("/gen/image_card")
def gen_image_card(cos_key: str):
    """单图战绩(可解释):它赢过谁、输给谁、平了几场。供图榜点开详情。"""
    rows = q("SELECT left_key, right_key, winner FROM gen_battle WHERE left_key=%s OR right_key=%s",
             (cos_key, cos_key))
    beat, lost = [], []; ties = 0; total = len(rows)
    for r in rows:
        opp = r["right_key"] if r["left_key"] == cos_key else r["left_key"]
        iwon = (r["winner"] == "left" and r["left_key"] == cos_key) or (r["winner"] == "right" and r["right_key"] == cos_key)
        ilost = r["winner"] in ("left", "right") and not iwon
        if r["winner"] == "tie": ties += 1
        elif iwon and opp not in [b["cos_key"] for b in beat]: beat.append({"cos_key": opp})
        elif ilost and opp not in [l["cos_key"] for l in lost]: lost.append({"cos_key": opp})
    pack = lambda arr: [{"cos_key": x["cos_key"], "thumb": img_url(x["cos_key"], 200)} for x in arr[:12]]
    return {"total": total, "ties": ties, "beat": pack(beat), "lost": pack(lost)}

@app.get("/gen/arena")
def gen_arena(limit: int = 30, category: str = None, axis: str = "overall"):
    """竞技场榜单。axis=镜头(overall综合/real去AI感/creative创意);category=题材子榜。
       图榜/做法榜用**眼光加权 BT**(高眼光评审票权更高);眼光本身仍按无权共识测,诚实。"""
    from collections import Counter
    if axis not in AXES: axis = "overall"
    allrows = q("SELECT left_key, right_key, winner, rater, axis FROM gen_battle")
    rows = [r for r in allrows if (r.get("axis") or "overall") == axis]   # 当前镜头
    gcount_all = {}
    for r in rows:
        gcount_all[r["left_key"]] = gcount_all.get(r["left_key"], 0) + 1
        gcount_all[r["right_key"]] = gcount_all.get(r["right_key"], 0) + 1
    keys = list(gcount_all.keys())
    meta = {}
    if keys:
        for x in q("""SELECT gf.cos_key, r.workflow_name wf, r.params->>'model' model,
                             gf.quality, gf.vlm->>'category' vcat, gf.category cat
                      FROM gen_file gf JOIN gen_run r ON r.instance_id=gf.instance_id
                      WHERE gf.cos_key = ANY(%s)""", (keys,)):
            meta[x["cos_key"]] = x
    catmap = {k: ((m.get("cat") or "").split("/")[-1] or None) for k, m in meta.items()}

    def mkpairs(subset, wts=None):
        pr = []; gc = {}
        for r in subset:
            a, b, w = r["left_key"], r["right_key"], r["winner"]
            gc[a] = gc.get(a, 0) + 1; gc[b] = gc.get(b, 0) + 1
            ww = wts.get(r["rater"], 1.0) if wts else 1.0
            if w == "left": pr.append((a, b, ww))
            elif w == "right": pr.append((b, a, ww))
            elif w == "tie": pr.append((a, b, 0.5 * ww)); pr.append((b, a, 0.5 * ww))
        return pr, gc

    # 题材 facet(本镜头内,双方同题材的对决数)
    catn = {}
    for r in rows:
        ca = catmap.get(r["left_key"]); cb = catmap.get(r["right_key"])
        if ca and ca == cb: catn[ca] = catn.get(ca, 0) + 1
    categories = sorted([{"cat": k, "n": v} for k, v in catn.items()], key=lambda x: -x["n"])

    # pass1:无权全局 BT → 评审眼光(只在双方各≥3场的对决上算,诚实)
    SETTLE = 3
    gpairs, _ = mkpairs(rows)
    btg = bt_scores(gpairs)
    eye = {}
    for r in rows:
        if r["winner"] not in ("left", "right"): continue
        a, b = r["left_key"], r["right_key"]
        chosen, other = (a, b) if r["winner"] == "left" else (b, a)
        if chosen not in btg or other not in btg: continue
        if gcount_all.get(chosen, 0) < SETTLE or gcount_all.get(other, 0) < SETTLE: continue
        e = eye.setdefault(r["rater"], [0, 0]); e[1] += 1
        if btg[chosen] >= btg[other]: e[0] += 1
    eye_val = {k: (v[0] / v[1] if v[1] >= 4 else None) for k, v in eye.items()}
    # pass2 权重:眼光 0.5→中性1.0、1.0→2.0、低于0.25 封底0.5;样本不足(None)中性
    weights = {k: (max(0.5, min(2.0, 2.0 * ev)) if ev is not None else 1.0) for k, ev in eye_val.items()}

    # 视图:按题材过滤 + 眼光加权
    sub = [r for r in rows if catmap.get(r["left_key"]) == category and catmap.get(r["right_key"]) == category] if category else rows
    vpairs, gcv = mkpairs(sub, weights)
    ci, bt = bt_ci(vpairs)
    def lob(k): return ci.get(k, (bt[k] - 400, bt[k] + 400))[0]
    top = sorted(bt.keys(), key=lambda k: -lob(k))[:limit]
    images = []
    for k in top:
        sc = round(bt[k]); lo, hi = ci.get(k, (bt[k] - 400, bt[k] + 400))
        lo = min(round(lo), sc); hi = max(round(hi), sc)
        images.append({"cos_key": k, "image": img_url(k, 500), "full": img_url(k), "score": sc, "lo": lo, "hi": hi,
                       "n": gcv.get(k, 0), "workflow": (meta.get(k) or {}).get("wf"),
                       "vlm_category": (meta.get(k) or {}).get("vcat"),
                       "settled": gcv.get(k, 0) >= 3})
    # 做法榜(按 workflow,随题材过滤 + 眼光加权)
    mpairs = []; mcount = {}
    for r in sub:
        a, b, w = r["left_key"], r["right_key"], r["winner"]
        wa = (meta.get(a) or {}).get("wf"); wb = (meta.get(b) or {}).get("wf")
        if not wa or not wb: continue
        ww = weights.get(r["rater"], 1.0)
        mcount[wa] = mcount.get(wa, 0) + 1; mcount[wb] = mcount.get(wb, 0) + 1
        if wa == wb: continue
        if w == "left": mpairs.append((wa, wb, ww))
        elif w == "right": mpairs.append((wb, wa, ww))
        elif w == "tie": mpairs.append((wa, wb, 0.5 * ww)); mpairs.append((wb, wa, 0.5 * ww))
    mbt = bt_scores(mpairs)
    wf_model = {}
    for k, m in meta.items():
        wf = m.get("wf"); md = m.get("model")
        if wf and md: wf_model.setdefault(wf, Counter())[md] += 1
    methods = sorted([{"workflow": k, "score": round(s), "n": mcount.get(k, 0),
                       "model": (wf_model[k].most_common(1)[0][0] if k in wf_model else None)}
                      for k, s in mbt.items()], key=lambda x: -x["score"])
    # 评审眼光榜(展示无权眼光)
    rnames = _rater_names(list(eye.keys()))
    raters = sorted([{"rater": k, "name": rnames.get(k) or k, "n": v[1],
                      "eye": round(v[0] / v[1], 3) if v[1] >= 4 else None,
                      "weight": round(weights.get(k, 1.0), 2)}
                     for k, v in eye.items()], key=lambda x: (-(x["eye"] or 0), -x["n"]))
    # 人评(无权 BT) vs AI(VLM quality)相关性 + 散点(供洞察可视化)
    xs, ys = [], []; scatter = []
    for k, s in btg.items():
        qy = (meta.get(k) or {}).get("quality")
        if qy is not None and gcount_all.get(k, 0) >= 2:
            xs.append(s); ys.append(float(qy))
            scatter.append({"score": round(s), "quality": round(float(qy), 3),
                            "settled": gcount_all.get(k, 0) >= 3})
    corr = _pearson(xs, ys)
    # 贡献榜:每位评审累计贡献的对决场数(全局,跨镜头/题材;含 tie/both_bad),用于致谢
    contrib = {}
    for r in allrows:
        contrib[r["rater"]] = contrib.get(r["rater"], 0) + 1
    cnames = _rater_names(list(contrib))
    contributors = sorted([{"rater": k, "name": cnames.get(k) or k, "n": v} for k, v in contrib.items()],
                          key=lambda x: -x["n"])[:50]
    # AI 质量基线(零新增 VLM:用已存 gf.quality):人评稀疏时先给个起点,人一投票就被真实 BT 取代
    baseline = []
    if len(images) < 6:
        bsql = ARENA_SCOPE + " AND gf.quality IS NOT NULL"
        bargs = []
        if category:
            bsql += " AND gf.category = %s"; bargs.append("art/" + category)
        for x in q(f"""SELECT gf.cos_key, gf.quality, r.workflow_name wf
                       FROM gen_file gf JOIN gen_run r ON r.instance_id=gf.instance_id
                       WHERE {bsql} ORDER BY gf.quality DESC LIMIT 18""", tuple(bargs)):
            baseline.append({"cos_key": x["cos_key"], "image": img_url(x["cos_key"], 500),
                             "full": img_url(x["cos_key"]), "quality": round(float(x["quality"]), 3),
                             "workflow": x["wf"]})
    return {"totals": {"battles": len(rows), "raters": len({r["rater"] for r in rows}), "images_touched": len(gcount_all)},
            "baseline": baseline,
            "axis": axis, "categories": categories, "category": category,
            "images": images, "methods": methods, "raters": raters, "scatter": scatter,
            "contributors": contributors,
            "human_vs_vlm_corr": (round(corr, 3) if corr is not None else None), "corr_n": len(xs)}

@app.get("/gen/battle/summary")
def gen_battle_summary(rater: str, session: str = None):
    """结论卡:该评审的眼光分(与全局 BT 共识一致率)、你 vs AI、口味倾向、独特一票、贡献。
       只用能可靠算出的信号(无 12 维审美标注,不输出门派)。"""
    rater = (rater or "").strip()[:40]
    if not rater: raise HTTPException(400, "no rater")
    allrows = q("SELECT left_key, right_key, winner FROM gen_battle")
    pairs = []
    for r in allrows:
        a, b, w = r["left_key"], r["right_key"], r["winner"]
        if w == "left": pairs.append((a, b, 1.0))
        elif w == "right": pairs.append((b, a, 1.0))
        elif w == "tie": pairs.append((a, b, 0.5)); pairs.append((b, a, 0.5))
    bt = bt_scores(pairs)
    SETTLE = 3        # 双方各比够这么多场,BT 分才代表"大众共识"而非"你这一票"(否则眼光会虚高到100%)
    gcount = {}
    for r in allrows:
        gcount[r["left_key"]] = gcount.get(r["left_key"], 0) + 1
        gcount[r["right_key"]] = gcount.get(r["right_key"], 0) + 1
    mine = q("SELECT left_key, right_key, winner, session FROM gen_battle WHERE rater=%s ORDER BY created_at", (rater,))
    total = len(mine)
    if total == 0: return {"total": 0}
    session_n = sum(1 for r in mine if session and r["session"] == session)
    touched = set()
    for r in mine:
        touched.add(r["left_key"]); touched.add(r["right_key"])
    meta = {}
    if touched:
        for x in q("SELECT cos_key, quality FROM gen_file WHERE cos_key = ANY(%s)", (list(touched),)):
            meta[x["cos_key"]] = x
    eye_a = eye_t = ai_a = ai_t = flips = 0
    chosen_keys = []
    for r in mine:
        if r["winner"] not in ("left", "right"): continue
        a, b = r["left_key"], r["right_key"]
        chosen, other = (a, b) if r["winner"] == "left" else (b, a)
        chosen_keys.append(chosen)
        if (chosen in bt and other in bt
                and gcount.get(chosen, 0) >= SETTLE and gcount.get(other, 0) >= SETTLE):
            eye_t += 1
            if bt[chosen] >= bt[other]: eye_a += 1
        qc = (meta.get(chosen) or {}).get("quality"); qo = (meta.get(other) or {}).get("quality")
        if qc is not None and qo is not None and qc != qo:
            ai_t += 1
            if qc > qo: ai_a += 1                                   # AI 也会挑你选的那张
            elif chosen in bt and other in bt and bt[chosen] > bt[other]: flips += 1  # 你和AI分歧,BT 证明你对
    eye = round(eye_a / eye_t, 3) if eye_t >= 4 else None   # 够格样本太少不给假眼光分
    vs_ai = round(ai_a / ai_t, 3) if ai_t >= 3 else None
    # 口味倾向:对你选为胜者的图,聚合色调 / 做法 / 审美维度。有 12 维标注(vlm_v2)优先用更细的语言7轴+情绪
    taste_lines = []
    if chosen_keys:
        from collections import Counter
        rows = q("""SELECT gf.hue, r.workflow_name wf, gf.vlm vlm, gf.vlm_v2 v2
                    FROM gen_file gf JOIN gen_run r ON r.instance_id=gf.instance_id
                    WHERE gf.cos_key = ANY(%s)""", (chosen_keys,))
        hue_c = Counter(); wf_c = Counter()
        axes = {"aesthetic": [], "technical": [], "composition": [], "coherence": []}
        v2vecs = []
        for x in rows:
            if x["hue"]: hue_c[x["hue"]] += 1
            if x["wf"]: wf_c[x["wf"]] += 1
            sc = (x["vlm"] or {}).get("scores") or {}
            for k in axes:
                if isinstance(sc.get(k), (int, float)): axes[k].append(sc[k])
            if x["v2"]:
                vv = aha_profile.work_vec(x["v2"])
                if vv: v2vecs.append(vv)
        if hue_c: taste_lines.append(f"你偏爱 {hue_c.most_common(1)[0][0]} 色调的画面")
        if wf_c: taste_lines.append(f"你最常挑中「{wf_c.most_common(1)[0][0]}」做法的图")
        if len(v2vecs) >= 3:        # 12 维标注够了:用语言7轴 + 情绪给更准的口味
            n = len(v2vecs)
            LANGLAB = ["构图", "空间", "造型", "光影", "色彩", "笔触", "边缘"]
            lavg = {}
            for i in range(7):
                vals = [v[2 + i] for v in v2vecs if v[2 + i] is not None]
                if vals: lavg[LANGLAB[i]] = sum(vals) / len(vals)
            if lavg:
                taste_lines.append(f"你更吃画面的「{max(lavg, key=lavg.get)}」")
            val = [v[9] for v in v2vecs if v[9] is not None]
            aro = [v[10] for v in v2vecs if v[10] is not None]
            if aro:
                a = sum(aro) / len(aro); vv = (sum(val) / len(val)) if val else 0.5
                mood = ("安静沉潜" if a < 0.4 else "热烈张力" if a > 0.62 else "舒展平和")
                tone = "明亮愉悦" if vv > 0.6 else ("低回内敛" if vv < 0.4 else "")
                taste_lines.append(f"你偏爱{mood}{('、' + tone) if tone else ''}的情绪")
        else:                       # 回退:旧的 4 轴质量分
            avg = {k: sum(v) / len(v) for k, v in axes.items() if v}
            if avg:
                lab = {"aesthetic": "美感", "technical": "技法", "composition": "构图", "coherence": "连贯"}
                taste_lines.append(f"你更看重画面的{lab[max(avg, key=avg.get)]}")
    # 独特一票:你选中、但全局 BT 排名最低的那张
    unique = None
    cand = sorted(((k, bt[k]) for k in chosen_keys if k in bt), key=lambda kv: kv[1])
    if cand:
        unique = {"thumb": img_url(cand[0][0], 300)}
    return {"total": total, "session_n": session_n, "images_helped": len(touched),
            "eye": eye, "eye_n": eye_t, "vs_ai": vs_ai, "ai_n": ai_t,
            "ai_flips": flips, "taste_lines": taste_lines, "unique": unique}

# ---------- 造物云素材库浏览/管理 ----------
@app.get("/zwy")
def zwy(category: str = None, kw: str = Query(None, alias="q"), color: str = None, fmt: str = None,
        date_from: str = None, date_to: str = None, ratio: str = None, sort: str = None,
        limit: int = 40, offset: int = 0):
    where = ["status='stored'"]; args = []
    if category: where.append("category=%s"); args.append(category)
    if color: where.append("hue=%s"); args.append(color)
    if fmt: where.append("type ILIKE %s"); args.append('%'+fmt+'%')
    if kw: where.append("display_name ILIKE %s"); args.append('%'+kw+'%')
    if date_from: where.append("created_ts >= %s"); args.append(date_from)
    if date_to: where.append("created_ts < (%s::date + 1)"); args.append(date_to)
    if ratio == "横": where.append("width > height*1.15")
    elif ratio == "竖": where.append("height > width*1.15")
    elif ratio == "方": where.append("abs(width-height) <= width*0.15")
    wsql = " AND ".join(where)
    order = {"大": "size DESC NULLS LAST", "高清": "width*height DESC NULLS LAST", "时间": "created_ts DESC NULLS LAST"}.get(sort, "created_ts DESC NULLS LAST")
    rows = q(f"""SELECT src_id, display_name, category, cls_conf, cos_key, width, height, size,
                        extract(epoch from created_ts) ct, type, ave_rgb, hue
                 FROM zaowuyun_media WHERE {wsql}
                 ORDER BY {order} OFFSET %s LIMIT %s""", args + [offset, limit])
    items = [{"src_id": r["src_id"], "name": r["display_name"], "category": r["category"],
              "conf": r["cls_conf"], "w": r["width"], "h": r["height"], "size": r["size"], "type": r["type"],
              "ave_rgb": r["ave_rgb"], "hue": r["hue"], "time": int(r["ct"]*1000) if r["ct"] else None,
              "thumb": img_url(r["cos_key"], 500), "image": img_url(r["cos_key"])} for r in rows]
    matched = q(f"SELECT count(*) n FROM zaowuyun_media WHERE {wsql}", args, one=True)["n"]
    return {"items": items, "matched": matched}

@app.get("/zwy/facets")
def zwy_facets():
    cats = q("SELECT category k, count(*) n FROM zaowuyun_media WHERE status='stored' AND category IS NOT NULL GROUP BY 1 ORDER BY 2 DESC")
    cols = q("SELECT hue k, count(*) n, mode() WITHIN GROUP (ORDER BY ave_rgb) rgb FROM zaowuyun_media WHERE status='stored' AND hue IS NOT NULL GROUP BY 1 ORDER BY 2 DESC")
    fmts = q("SELECT split_part(type,'/',2) k, count(*) n FROM zaowuyun_media WHERE status='stored' AND type IS NOT NULL GROUP BY 1 ORDER BY 2 DESC")
    span = q("SELECT to_char(min(created_ts),'YYYY-MM-DD') lo, to_char(max(created_ts),'YYYY-MM-DD') hi FROM zaowuyun_media WHERE status='stored'", one=True)
    tot = q("SELECT count(*) all, count(*) filter(where status='stored') stored, count(*) filter(where status='pending') pending, count(*) filter(where status='err') err, coalesce(sum(size) filter(where status='stored'),0) bytes FROM zaowuyun_media", one=True)
    return {"categories": [{"k": c["k"], "n": c["n"]} for c in cats],
            "colors": [{"k": c["k"], "n": c["n"], "rgb": c["rgb"]} for c in cols],
            "formats": [{"k": c["k"], "n": c["n"]} for c in fmts if c["k"]],
            "span": {"lo": span["lo"], "hi": span["hi"]},
            "total": tot["all"], "stored": tot["stored"], "pending": tot["pending"], "err": tot["err"],
            "gb": round(tot["bytes"]/1073741824, 2)}

@app.post("/zwy/recat")
def zwy_recat(src_id: str, category: str):
    """人工改分类(内容管理)。若改成/移出油画,同步生成区 gen_file。"""
    r = q("SELECT cos_key, sha256, phash, width, height, type, display_name, src_url FROM zaowuyun_media WHERE src_id=%s", (src_id,), one=True)
    if not r: raise HTTPException(404, "not found")
    ex("UPDATE zaowuyun_media SET category=%s WHERE src_id=%s", (category, src_id))
    ex("DELETE FROM gen_file WHERE src_id=%s AND source='zaowuyun'", (src_id,))
    if category == "油画":
        ex("""INSERT INTO gen_file(instance_id,cos_key,sha256,phash,width,height,fmt,role,q_status,source,category,src_id,display_name)
              VALUES(NULL,%s,%s,%s,%s,%s,%s,'output','pending','zaowuyun','油画',%s,%s) ON CONFLICT(cos_key) DO NOTHING""",
           (r["cos_key"], r["sha256"], r["phash"], r["width"], r["height"], (r["type"] or "").split("/")[-1] or "jpg", src_id, r["display_name"]))
    return {"ok": True, "category": category}

_ZWY_COS = {"cl": None}
def _zwy_cos():
    if _ZWY_COS["cl"] is None:
        from qcloud_cos import CosS3Client, CosConfig
        d = json.load(open(os.path.expanduser("~/.aha_cos.json")))
        _ZWY_COS["cl"] = CosS3Client(CosConfig(Region=d["region"], SecretId=d["secret_id"], SecretKey=d["secret_key"], Timeout=20))
    return _ZWY_COS["cl"]

@app.get("/zwy/detail")
def zwy_detail(src_id: str):
    """单张素材完整元数据(详情面板)。"""
    r = q("""SELECT src_id, display_name, description, type, src_url, size, md5,
                    extract(epoch from created_ts) ct, category, cls_conf, cos_key,
                    width, height, ave_rgb, hue, meta
             FROM zaowuyun_media WHERE src_id=%s""", (src_id,), one=True)
    if not r: raise HTTPException(404, "not found")
    m = r["meta"] or {}
    tags = m.get("assetTags") or []
    return {"src_id": r["src_id"], "name": r["display_name"], "description": r["description"],
            "type": r["type"], "size": r["size"], "md5": r["md5"],
            "time": int(r["ct"]*1000) if r["ct"] else None, "category": r["category"], "conf": r["cls_conf"],
            "w": r["width"], "h": r["height"], "ave_rgb": r["ave_rgb"], "hue": r["hue"],
            "creator": m.get("creatorUserId"), "src_url": r["src_url"],
            "tags": [(t.get("name") if isinstance(t, dict) else t) for t in tags] if tags else [],
            "image": img_url(r["cos_key"])}

@app.get("/zwy/timeline")
def zwy_timeline():
    """按天的生成量分布(供时间轴),含起止与每天计数。"""
    rows = q("""SELECT to_char(created_ts::date,'YYYY-MM-DD') d, count(*) n
                FROM zaowuyun_media WHERE status='stored' AND created_ts IS NOT NULL
                GROUP BY 1 ORDER BY 1""")
    return {"days": [{"d": r["d"], "n": r["n"]} for r in rows],
            "total": sum(r["n"] for r in rows)}

@app.post("/zwy/delete")
def zwy_delete(src_id: str):
    """删除一张素材:删COS对象 + 移出生成区 + 标 deleted(留行可审计)。"""
    r = q("SELECT cos_key, status FROM zaowuyun_media WHERE src_id=%s", (src_id,), one=True)
    if not r: raise HTTPException(404, "not found")
    if r["cos_key"]:
        try: _zwy_cos().delete_object(Bucket="aha-1254041526", Key=r["cos_key"])
        except Exception: pass
    ex("DELETE FROM gen_file WHERE src_id=%s AND source='zaowuyun'", (src_id,))
    ex("UPDATE zaowuyun_media SET status='deleted' WHERE src_id=%s", (src_id,))
    return {"ok": True}

@app.post("/zwy/delete_batch")
def zwy_delete_batch(ids: str):
    """批量删除:删COS对象 + 移出生成区 + 标 deleted。ids=逗号分隔的 src_id。"""
    id_list = [i for i in (ids or "").split(",") if i][:1000]
    n = 0
    for sid in id_list:
        r = q("SELECT cos_key FROM zaowuyun_media WHERE src_id=%s AND status<>'deleted'", (sid,), one=True)
        if not r: continue
        if r["cos_key"]:
            try: _zwy_cos().delete_object(Bucket="aha-1254041526", Key=r["cos_key"])
            except Exception: pass
        ex("DELETE FROM gen_file WHERE src_id=%s AND source='zaowuyun'", (sid,))
        ex("UPDATE zaowuyun_media SET status='deleted' WHERE src_id=%s", (sid,))
        n += 1
    return {"ok": True, "deleted": n}

# ---------- 造物云AI生成区浏览(新团队) ----------
@app.get("/zwy/gen")
def zwy_gen(category: str = None, kw: str = Query(None, alias="q"), model: str = None,
            wf: str = None, date_from: str = None, date_to: str = None,
            sort: str = None, limit: int = 40, offset: int = 0):
    """浏览造物云新团队的AI生成数据(gen_run+gen_file, source='zaowuyun_team')。"""
    where = ["gr.source='zaowuyun_team'", "gf.role='output'"]; args = []
    if category:
        if '/' in category:
            where.append("gf.category=%s"); args.append(category)
        else:
            where.append("gf.category LIKE %s"); args.append(category + '/%')
    if model: where.append("gr.params->>'model'=%s"); args.append(model)
    if wf: where.append("gr.workflow_name=%s"); args.append(wf)
    if kw: where.append("gr.input_prompt ILIKE %s"); args.append('%'+kw+'%')
    if date_from: where.append("gr.start_time >= %s"); args.append(date_from)
    if date_to: where.append("gr.start_time < (%s::date + 1)"); args.append(date_to)
    wsql = " AND ".join(where)
    order = {"最新": "gr.start_time DESC NULLS LAST", "高清": "gf.width*gf.height DESC NULLS LAST", "大图": "gf.bytes DESC NULLS LAST"}.get(sort, "gr.start_time DESC NULLS LAST")
    rows = q(f"""SELECT gr.instance_id, gr.workflow_name, gr.status, gr.input_prompt, gr.final_prompt,
                        gr.system_prompt, gr.seed,
                        gr.params->>'model' model, gr.start_time, gr.params,
                        gf.cos_key, gf.width, gf.height, gf.bytes, gf.fmt, gf.ave_rgb, gf.hue, gf.category,
                        gf.q_status, gf.quality
                 FROM gen_run gr JOIN gen_file gf ON gr.instance_id=gf.instance_id
                 WHERE {wsql}
                 ORDER BY {order} OFFSET %s LIMIT %s""", args + [offset, limit])
    items = [{"instance_id": r["instance_id"], "workflow": r["workflow_name"], "status": r["status"],
              "prompt": r["input_prompt"], "final_prompt": r["final_prompt"],
              "system_prompt": r["system_prompt"], "seed": r["seed"],
              "model": r["model"], "category": r["category"],
              "w": r["width"], "h": r["height"], "size": r["bytes"], "fmt": r["fmt"],
              "ave_rgb": r["ave_rgb"], "hue": r["hue"],
              "q_status": r["q_status"], "quality": r["quality"],
              "time": int(r["start_time"].timestamp()*1000) if r["start_time"] else None,
              "params": r["params"],
              "thumb": img_url(r["cos_key"], 500), "image": img_url(r["cos_key"])} for r in rows]
    matched = q(f"SELECT count(*) n FROM gen_run gr JOIN gen_file gf ON gr.instance_id=gf.instance_id WHERE {wsql}", args, one=True)["n"]
    return {"items": items, "matched": matched}

@app.get("/zwy/gen/facets")
def zwy_gen_facets():
    """造物云AI生成区的筛选面板。"""
    wfs = q("SELECT workflow_name k, count(*) n FROM gen_run WHERE source='zaowuyun_team' GROUP BY 1 ORDER BY 2 DESC")
    models = q("SELECT params->>'model' k, count(*) n FROM gen_run WHERE source='zaowuyun_team' AND params->>'model' IS NOT NULL GROUP BY 1 ORDER BY 2 DESC")
    colors = q("SELECT gf.hue k, count(*) n, mode() WITHIN GROUP (ORDER BY gf.ave_rgb) rgb FROM gen_run gr JOIN gen_file gf ON gr.instance_id=gf.instance_id WHERE gr.source='zaowuyun_team' AND gf.role='output' AND gf.hue IS NOT NULL GROUP BY 1 ORDER BY 2 DESC")
    # 分类统计（大类 + 子类）
    cats_raw = q("SELECT category, count(*) n FROM gen_file WHERE source='zaowuyun_team' AND role='output' AND category IS NOT NULL GROUP BY 1 ORDER BY 2 DESC")
    cats_major = {}; cats_sub = []
    for r in cats_raw:
        cat = r["category"]; n = r["n"]
        cats_sub.append({"k": cat, "n": n})
        major = cat.split("/")[0] if "/" in cat else cat
        cats_major[major] = cats_major.get(major, 0) + n
    cats_major_list = [{"k": k, "n": n} for k, n in sorted(cats_major.items(), key=lambda x: -x[1])]
    span = q("SELECT to_char(min(start_time),'YYYY-MM-DD') lo, to_char(max(start_time),'YYYY-MM-DD') hi FROM gen_run WHERE source='zaowuyun_team' AND start_time IS NOT NULL", one=True)
    tot = q("SELECT count(*) runs FROM gen_run WHERE source='zaowuyun_team'", one=True)
    imgs = q("SELECT count(*) imgs, coalesce(sum(bytes),0) bytes FROM gen_file WHERE source='zaowuyun_team' AND role='output'", one=True)
    return {"workflows": [{"k": r["k"], "n": r["n"]} for r in wfs],
            "models": [{"k": r["k"], "n": r["n"]} for r in models],
            "colors": [{"k": r["k"], "n": r["n"], "rgb": r["rgb"]} for r in colors],
            "categories": cats_major_list,
            "categories_sub": cats_sub,
            "span": {"lo": span["lo"], "hi": span["hi"]} if span["lo"] else None,
            "total_runs": tot["runs"], "total_images": imgs["imgs"],
            "gb": round(imgs["bytes"]/1073741824, 2)}

@app.get("/zwy/gen/timeline")
def zwy_gen_timeline():
    """造物云AI生成区的每日时间线。"""
    rows = q("SELECT to_char(start_time::date,'YYYY-MM-DD') d, count(*) n "
             "FROM gen_run WHERE source='zaowuyun_team' AND start_time IS NOT NULL GROUP BY 1 ORDER BY 1")
    return {"days": [{"d": r["d"], "n": r["n"]} for r in rows], "total": sum(r["n"] for r in rows)}

@app.get("/zwy/gen/detail")
def zwy_gen_detail(instance_id: str):
    """单条生成记录的完整元数据。"""
    r = q("""SELECT gr.instance_id, gr.workflow_id, gr.workflow_name, gr.status,
                    gr.input_prompt, gr.final_prompt, gr.system_prompt,
                    gr.input_images, gr.seed, gr.params, gr.start_time, gr.end_time, gr.raw,
                    gf.cos_key, gf.src_url, gf.sha256, gf.phash, gf.width, gf.height, gf.bytes, gf.fmt,
                    gf.ave_rgb, gf.hue, gf.q_status, gf.quality, gf.category
             FROM gen_run gr LEFT JOIN gen_file gf ON gr.instance_id=gf.instance_id AND gf.role='output'
             WHERE gr.instance_id=%s""", (instance_id,), one=True)
    if not r: raise HTTPException(404, "not found")
    return {"instance_id": r["instance_id"], "workflow_id": r["workflow_id"],
            "workflow": r["workflow_name"], "status": r["status"],
            "prompt": r["input_prompt"], "final_prompt": r["final_prompt"],
            "system_prompt": r["system_prompt"],
            "input_images": r["input_images"], "seed": r["seed"],
            "params": r["params"], "raw": r["raw"], "category": r["category"],
            "start_time": int(r["start_time"].timestamp()*1000) if r["start_time"] else None,
            "end_time": int(r["end_time"].timestamp()*1000) if r["end_time"] else None,
            "cos_key": r["cos_key"], "src_url": r["src_url"],
            "sha256": r["sha256"], "phash": r["phash"],
            "w": r["width"], "h": r["height"], "bytes": r["bytes"], "fmt": r["fmt"],
            "ave_rgb": r["ave_rgb"], "hue": r["hue"],
            "q_status": r["q_status"], "quality": r["quality"],
            "image": img_url(r["cos_key"]) if r["cos_key"] else None,
            "thumb": img_url(r["cos_key"], 500) if r["cos_key"] else None}

# ── 投票（赞/踩）──
@app.post("/zwy/vote")
def zwy_vote(instance_id: str, score: int, voter: str = "anonymous"):
    """投票: score=1 赞, score=-1 踩。重复投票更新。"""
    if score not in (1, -1): raise HTTPException(400, "score must be 1 or -1")
    ex("""INSERT INTO gen_vote (instance_id, voter, score) VALUES (%s, %s, %s)
          ON CONFLICT (instance_id, voter) DO UPDATE SET score=EXCLUDED.score, created_at=now()""",
       (instance_id, voter[:40], score))
    return {"ok": True}

@app.get("/zwy/votes")
def zwy_votes_get(ids: str = ""):
    """批量查询投票状态。ids=逗号分隔的 instance_id。"""
    if not ids: return {}
    id_list = ids.split(",")
    rows = q(f"""SELECT instance_id, SUM(CASE WHEN score=1 THEN 1 ELSE 0 END) AS likes,
                        SUM(CASE WHEN score=-1 THEN 1 ELSE 0 END) AS dislikes
                 FROM gen_vote WHERE instance_id = ANY(%s) GROUP BY 1""", (id_list,))
    return {r["instance_id"]: {"likes": r["likes"], "dislikes": r["dislikes"]} for r in rows}

@app.get("/zwy/voted")
def zwy_voted(voter: str = "anonymous"):
    """返回该用户的所有投票记录 {instance_id: score}。"""
    rows = q("SELECT instance_id, score FROM gen_vote WHERE voter=%s", (voter,))
    return {r["instance_id"]: r["score"] for r in rows}

@app.get("/zwy/top")
def zwy_top(limit: int = 50):
    """点赞最多的作品排行。"""
    rows = q("""SELECT v.instance_id, SUM(v.score) AS net, COUNT(*) AS votes,
                       gf.cos_key, gf.width, gf.height, gf.category, gr.input_prompt
                FROM gen_vote v
                JOIN gen_file gf ON gf.instance_id=v.instance_id AND gf.role='output'
                JOIN gen_run gr ON gr.instance_id=v.instance_id
                GROUP BY 1, gf.cos_key, gf.width, gf.height, gf.category, gr.input_prompt
                HAVING SUM(v.score) > 0
                ORDER BY net DESC LIMIT %s""", (limit,))
    return [{"instance_id": r["instance_id"], "net": r["net"], "votes": r["votes"],
             "image": img_url(r["cos_key"]), "thumb": img_url(r["cos_key"], 500),
             "w": r["width"], "h": r["height"], "category": r["category"],
             "prompt": r["input_prompt"]} for r in rows]

# CLIP 模型缓存
_clip_model = None
_clip_device = None

def get_clip_model():
    global _clip_model, _clip_device
    if _clip_model is None:
        import torch, clip
        _clip_device = "cuda" if torch.cuda.is_available() else "cpu"
        _clip_model, _ = clip.load("ViT-B/32", device=_clip_device)
    return _clip_model, _clip_device

@app.get("/zwy/search")
def zwy_semantic_search(query: str = Query("", alias="q"), limit: int = 30, category: str = ""):
    """语义搜索：用 CLIP 对查询文本编码，通过 pgvector HNSW 索引快速检索。"""
    if not query: return []
    import numpy as np, torch, clip as clip_module
    try:
        model, device = get_clip_model()
        text_tok = clip_module.tokenize([query]).to(device)
        with torch.no_grad():
            text_emb = model.encode_text(text_tok)
            text_emb = text_emb / text_emb.norm(dim=-1, keepdim=True)
        text_vec = text_emb.cpu().numpy().astype(np.float32).flatten()
        vec_str = '[' + ','.join(f'{v:.6f}' for v in text_vec) + ']'
    except Exception as e:
        raise HTTPException(500, f"CLIP error: {e}")

    # 通过 pgvector HNSW 索引快速检索
    cat_filter = ""
    if category:
        cat_filter = f"AND gf.category LIKE '{category}%'"

    rows = q(f"""SELECT gc.instance_id, 1 - (gc.embedding_vec <=> %s::vector) as score,
                       gf.cos_key, gf.width, gf.height, gf.category,
                       gr.input_prompt, gr.start_time
                FROM gen_clip gc
                JOIN gen_file gf ON gf.instance_id=gc.instance_id AND gf.role='output'
                JOIN gen_run gr ON gr.instance_id=gc.instance_id
                WHERE gc.embedding_vec IS NOT NULL AND gf.source='zaowuyun_team' {cat_filter}
                ORDER BY gc.embedding_vec <=> %s::vector
                LIMIT %s""", (vec_str, vec_str, limit))

    return [{"instance_id": r["instance_id"], "score": round(float(r["score"]), 4),
             "image": img_url(r["cos_key"]), "thumb": img_url(r["cos_key"], 500),
             "w": r["width"], "h": r["height"], "category": r["category"],
             "prompt": r["input_prompt"],
             "time": int(r["start_time"].timestamp()*1000) if r["start_time"] else None} for r in rows]

@app.get("/zwy/similar")
def zwy_similar(instance_id: str, limit: int = 12):
    """以图搜图：根据 instance_id 找相似图片。"""
    # 获取该图片的 embedding
    row = q("SELECT embedding_vec::text FROM gen_clip WHERE instance_id=%s AND embedding_vec IS NOT NULL", (instance_id,), one=True)
    if not row: return []

    vec_str = row["embedding_vec"]
    rows = q("""SELECT gc.instance_id, 1 - (gc.embedding_vec <=> %s::vector) as score,
                       gf.cos_key, gf.width, gf.height, gf.category, gr.input_prompt
                FROM gen_clip gc
                JOIN gen_file gf ON gf.instance_id=gc.instance_id AND gf.role='output'
                JOIN gen_run gr ON gr.instance_id=gc.instance_id
                WHERE gc.embedding_vec IS NOT NULL AND gc.instance_id != %s AND gf.source='zaowuyun_team'
                ORDER BY gc.embedding_vec <=> %s::vector
                LIMIT %s""", (vec_str, instance_id, vec_str, limit))

    return [{"instance_id": r["instance_id"], "score": round(float(r["score"]), 4),
             "image": img_url(r["cos_key"]), "thumb": img_url(r["cos_key"], 500),
             "w": r["width"], "h": r["height"], "category": r["category"],
             "prompt": r["input_prompt"]} for r in rows]

@app.get("/gen/stats")
def gen_stats():
    """生成区统计:artist 平台 + 造物云艺术数据。"""
    src = "(source IS NULL OR (source='zaowuyun_team' AND instance_id IN (SELECT instance_id FROM gen_file WHERE category LIKE 'art/%%')))"
    tot = q(f"SELECT count(*) n FROM gen_run WHERE {src}", one=True)["n"]
    imgs = q(f"SELECT count(*) n FROM gen_file gf JOIN gen_run gr ON gr.instance_id=gf.instance_id WHERE gf.role='output' AND (gr.source IS NULL OR (gr.source='zaowuyun_team' AND gf.category LIKE 'art/%%'))", one=True)["n"]
    span = q(f"SELECT to_char(min(start_time),'YYYY-MM-DD') lo, to_char(max(start_time),'YYYY-MM-DD') hi "
             f"FROM gen_run WHERE start_time IS NOT NULL AND {src}", one=True)
    avgr = q(f"SELECT round(extract(epoch from avg(end_time-start_time))) avgsec "
             f"FROM gen_run WHERE status='COMPLETED' AND end_time > start_time AND {src}", one=True)
    byday = q(f"SELECT to_char(start_time::date,'YYYY-MM-DD') d, count(*) n "
              f"FROM gen_run WHERE start_time IS NOT NULL AND {src} GROUP BY 1 ORDER BY 1")
    bywf = q(f"SELECT workflow_name wf, count(*) n FROM gen_run WHERE {src} GROUP BY 1 ORDER BY 2 DESC")
    bist = q(f"SELECT status, count(*) n FROM gen_run WHERE {src} GROUP BY 1 ORDER BY 2 DESC")
    return {"total_runs": tot, "total_images": imgs,
            "span": {"lo": span["lo"], "hi": span["hi"], "avg_sec": avgr["avgsec"]},
            "by_day": [{"d": r["d"], "n": r["n"]} for r in byday],
            "by_workflow": [{"workflow": r["wf"], "n": r["n"]} for r in bywf],
            "by_status": [{"status": r["status"], "n": r["n"]} for r in bist]}
