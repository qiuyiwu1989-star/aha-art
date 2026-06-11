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

import profile as aha_profile  # 审美档案/推荐引擎(同目录)
_d = json.load(open(os.path.expanduser("~/.aha_pg.json")))
POOL = ThreadedConnectionPool(1, 8, host=_d["host"], port=_d["port"], dbname=_d["dbname"],
                              user=_d["user"], password=_d["password"])
COS_BASE = "https://aha-1254041526.cos.ap-shanghai.myqcloud.com/"

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

def img_url(cos_key, thumb=None):
    if not cos_key: return None
    if cos_key.startswith("img/"):       # demo226 本地图:走 nginx 静态根,不加 COS/imageMogr2
        return "/" + cos_key
    u = COS_BASE + quote(cos_key, safe="/")
    return u + f"?imageMogr2/thumbnail/{thumb}x" if thumb else u

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
    rows = q(f"""SELECT w.work_id, w.title, a.name_cn, a.name_en, w.year, w.quality,
                        s.name_zh style_zh,
                        w.vlm->'affect'->>'primary_anchor' anchor,
                        f.cos_key, f.width, f.height
                 FROM works w JOIN artists a ON a.artist_id=w.artist_id
                 JOIN files f ON f.file_id=w.primary_file_id
                 LEFT JOIN styles s ON s.style_id=w.style_id
                 WHERE {wsql} ORDER BY w.quality DESC NULLS LAST, w.work_id
                 OFFSET %s LIMIT %s""", args + [offset, limit])
    items = [{"id": r["work_id"], "title": r["title"],
              "artist": r["name_cn"] or r["name_en"], "year": r["year"],
              "style": r["style_zh"], "quality": r["quality"], "anchor": r["anchor"],
              "thumb": img_url(r["cos_key"], thumb), "full": img_url(r["cos_key"]),
              "w": r["width"], "h": r["height"]} for r in rows]
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

@app.get("/exhibit")
def exhibit(limit: int = 3000, collection: int = None):
    """展出集(供 art.html 消费),输出对齐 gallery_works.json 形态。仅含已 exhibited 且有世界观坐标的。"""
    where = "w.exhibited"; args = []   # 放开门槛:全部 exhibited,有坐标的落世界观平面,没坐标的照常看
    if collection:
        where = "w.work_id IN (SELECT work_id FROM collection_works WHERE collection_id=%s)"
        args = [collection]
    rows = q(f"""SELECT w.work_id, w.title, a.name_cn, a.name_en, a.region, w.artist_id, w.year, w.quality,
                        w.vlm, s.name_zh style_zh, f.cos_key
                 FROM works w JOIN artists a ON a.artist_id=w.artist_id JOIN files f ON f.file_id=w.primary_file_id
                 LEFT JOIN styles s ON s.style_id=w.style_id
                 WHERE {where} ORDER BY w.quality DESC NULLS LAST LIMIT %s""", args + [limit])
    works = []
    for r in rows:
        v = r["vlm"] or {}; wv = v.get("worldview") or {}; af = v.get("affect") or {}; vad = af.get("vad") or {}
        import re as _re2; _m = _re2.search(r"WV[1-6]", str(wv.get("wv") or "")); _wvc = _m.group(0) if _m else None
        L7 = v.get("language7") or {}
        lang = {}
        for full, short in _L7MAP.items():
            o = L7.get(full); lang[short] = (o.get("v") if isinstance(o, dict) else o) if o is not None else None
        # 装裱匹配信号:流派 style(规范库 name_zh 优先,回落 vlm.style.流派) + 媒材 medium(清掉「①绘画类型:」前缀)
        _vs = v.get("style") or {}
        style = r["style_zh"] or (_vs.get("流派") if isinstance(_vs, dict) else None)
        medium = v.get("media")
        if isinstance(medium, str):
            medium = _re2.sub(r"^[①-⑳\s]*绘画类型[:：]?\s*", "", medium).strip() or None
        works.append({"work_id": r["work_id"], "file": img_url(r["cos_key"]), "thumb": img_url(r["cos_key"], 600),
                      "title": r["title"] or "无题", "artist": r["name_cn"] or r["name_en"] or "佚名",
                      "aid": r["artist_id"], "year": r["year"], "region": r["region"], "wv": _wvc,
                      "wvcn": _WVN.get(_wvc), "x": wv.get("x"), "y": wv.get("y"),
                      "emo": af.get("primary_anchor"), "voiceover": v.get("voiceover"),
                      "vad": {"v": vad.get("valence"), "a": vad.get("arousal"), "d": vad.get("dominance")},
                      "color": v.get("color"), "lang": lang, "style": style, "medium": medium})
    return {"works": works, "n": len(works)}

@app.get("/foryou")
def foryou(uid: str, limit: int = 24):
    """个性化推荐(reward 内核):供 me.html「为你推荐」与画廊个性化排序。"""
    return aha_profile.foryou(uid, limit=limit)

@app.get("/me/profile")
def me_profile(uid: str):
    """读用户 12 维审美档案(供画廊/详情页做个性化展示)。"""
    return aha_profile.compute_profile(uid)

@app.get("/artists_canon")
def artists_canon():
    rows = q("""SELECT c.canon_id, c.cn, c.en, c.region, c.born, c.death,
                  (SELECT count(*) FROM works w JOIN artists a ON a.artist_id=w.artist_id
                   WHERE a.aha_kg_id=c.canon_id AND w.status='kept') n_kept
                FROM artists_canon c ORDER BY n_kept DESC, c.cn""")
    arts = []
    for r in rows:
        arts.append({"id": r["canon_id"], "cn": r["cn"], "en": r["en"], "region": r["region"],
                     "born": r["born"], "death": r["death"], "n": r["n_kept"]})
    # 补 wv 坐标(从 lore)
    wvm = {x["canon_id"]: x["lore"].get("wv") if x["lore"] else None for x in q("SELECT canon_id, lore FROM artists_canon")}
    for a in arts:
        wv = wvm.get(a["id"]) or {}
        a["wx"] = wv.get("x"); a["wy"] = wv.get("y"); a["wv"] = wv.get("region_id")
    return {"n": len(arts), "artists": arts}

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
        src = [id]
    a = q("SELECT artist_id,name_cn,name_en,born,death,region,nationality FROM artists WHERE artist_id=%s", (id if not canon_id else src[0],), one=True) or {}
    rows = q("""SELECT w.work_id,w.title,w.quality,s.name_zh style_zh,w.vlm,f.cos_key
                FROM works w JOIN files f ON f.file_id=w.primary_file_id LEFT JOIN styles s ON s.style_id=w.style_id
                WHERE w.artist_id = ANY(%s) AND w.status='kept' AND w.vlm IS NOT NULL
                ORDER BY w.quality DESC NULLS LAST LIMIT 160""", (src,))
    import re as _r
    works = []; stylec = {}; vs = []; as_ = []; wvpts = []
    for r in rows:
        v = r["vlm"] or {}; af = v.get("affect") or {}; vad = af.get("vad") or {}; wv = v.get("worldview") or {}
        if r["style_zh"]: stylec[r["style_zh"]] = stylec.get(r["style_zh"], 0) + 1
        if vad.get("valence") is not None: vs.append(float(vad["valence"])); as_.append(float(vad.get("arousal") or 0))
        item = {"id": r["work_id"], "title": r["title"] or "无题", "thumb": img_url(r["cos_key"], 300),
                "anchor": af.get("primary_anchor"), "style": r["style_zh"], "quality": r["quality"]}
        if wv.get("x") is not None:
            mw = _r.search(r"WV[1-6]", str(wv.get("wv") or ""))
            item["wx"] = wv.get("x"); item["wy"] = wv.get("y"); item["wv"] = mw.group(0) if mw else None
            wvpts.append(item)
        item["v"] = vad.get("valence"); item["a"] = vad.get("arousal")
        works.append(item)
    tot = q("SELECT count(*) c FROM works WHERE artist_id = ANY(%s) AND status='kept'", (src,), one=True)["c"]
    cen = {"v": round(sum(vs)/len(vs), 3), "a": round(sum(as_)/len(as_), 3)} if vs else None
    styles = [{"k": k, "n": n} for k, n in sorted(stylec.items(), key=lambda x: -x[1])]
    lore = canon["lore"] if canon else None
    return {"id": canon_id or a.get("artist_id") or id, "canon_id": canon_id,
            "name_cn": (canon["cn"] if canon else a.get("name_cn")),
            "name_en": (canon["en"] if canon else a.get("name_en")),
            "born": (canon["born"] if canon else a.get("born")),
            "death": (canon["death"] if canon else a.get("death")),
            "region": (canon["region"] if canon else a.get("region")),
            "nationality": (canon["nationality"] if canon else a.get("nationality")),
            "curated": bool(canon), "lore": lore,
            "n_kept": tot, "n_sources": len(src), "vad_centroid": cen,
            "styles": styles, "wv_points": wvpts, "works": works}

@app.get("/work/{wid}")
def work(wid: int):
    r = q("""SELECT w.work_id, w.title, w.year, w.school, s.name_zh style_zh, w.medium, w.w_cm, w.h_cm,
                    w.status, w.quality, w.vlm, w.source_batch,
                    a.name_cn, a.name_en, a.born, a.death, a.region,
                    f.cos_key, f.width, f.height
             FROM works w JOIN artists a ON a.artist_id=w.artist_id
             JOIN files f ON f.file_id=w.primary_file_id
             LEFT JOIN styles s ON s.style_id=w.style_id WHERE w.work_id=%s""", (wid,), one=True)
    if not r: raise HTTPException(404, "work not found")
    return {"id": r["work_id"], "title": r["title"], "year": r["year"],
            "school": r["style_zh"] or r["school"],
            "medium": r["medium"], "w_cm": r["w_cm"], "h_cm": r["h_cm"],
            "status": r["status"], "quality": r["quality"], "source": r["source_batch"],
            "artist": {"name_cn": r["name_cn"], "name_en": r["name_en"],
                       "born": r["born"], "death": r["death"], "region": r["region"]},
            "image": {"full": img_url(r["cos_key"]), "thumb": img_url(r["cos_key"], 800),
                      "w": r["width"], "h": r["height"]},
            "vlm": r["vlm"]}

@app.get("/related/{wid}")
def related(wid: int, limit: int = 8):
    """单幅画的相关作品:同一画家 → 同一情绪锚点 → 同一风格,去重。"""
    base = q("SELECT artist_id, style_id, vlm->'affect'->>'primary_anchor' anchor "
             "FROM works WHERE work_id=%s", (wid,), one=True)
    if not base:
        raise HTTPException(404, "work not found")
    seen = {wid}
    out = []
    SEL = ("SELECT w.work_id, w.title, a.name_cn, a.name_en, f.cos_key, %s rel "
           "FROM works w JOIN artists a ON a.artist_id=w.artist_id "
           "JOIN files f ON f.file_id=w.primary_file_id "
           "WHERE w.status='kept' AND w.work_id<>%s AND {cond} "
           "ORDER BY w.quality DESC NULLS LAST LIMIT %s")
    def add(rel, cond, val, n):
        for r in q(SEL.format(cond=cond), (rel, wid, val, n)):
            if r["work_id"] in seen:
                continue
            seen.add(r["work_id"])
            out.append({"id": r["work_id"], "title": r["title"],
                        "artist": r["name_cn"] or r["name_en"],
                        "thumb": img_url(r["cos_key"], 400), "rel": r["rel"]})
    if base["artist_id"]:
        add("同一画家", "w.artist_id=%s", base["artist_id"], 4)
    if base["anchor"]:
        add("同一情绪", "w.vlm->'affect'->>'primary_anchor'=%s", base["anchor"], 6)
    if base["style_id"]:
        add("同一风格", "w.style_id=%s", base["style_id"], 6)
    return {"items": out[:limit]}
