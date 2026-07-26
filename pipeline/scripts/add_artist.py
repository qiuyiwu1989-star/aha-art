#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""半自动新增一位艺术家到 aha 知识图谱。

你只给几项基本信息(中英文名/生卒/国籍/东西方/流派),脚本调 mimo LLM 起草整套 V3 深度档案
(世界观坐标 / 七大构成 / 情绪 VAD / 轨迹 / 师承 / 题材 / 画外音 / 意义),你审一眼确认后:
  1) 写进主档 data/kg_artists.json(自动备份 + 同步部署到 /data/pub/p/aha)
  2)(--sync)跑 ingest_canon_artists.py 灌进 Postgres → kg-artists/kg-artist 页面实时反映
  3)(--portrait FILE)安装头像到 img/portraits/ 并登记

铁律:引文 quote 必须真实或留空,绝不编造(沿用 aha 一贯规矩)。

用法:
  python3 add_artist.py --cn 席勒 --en "Egon Schiele" --born 1890 --death 1918 \
      --nationality 奥地利 --region west --styles 表现主义,维也纳分离派 --sync
  python3 add_artist.py            # 不带参数则交互式逐项询问
"""
import os, re, sys, json, time, shutil, argparse, unicodedata, subprocess, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO_JSON = "/home/ubuntu/users/qiuyiwu/aha-art-demo/data/kg_artists.json"
PUB_JSON  = "/data/pub/p/aha/data/kg_artists.json"
PORTRAITS_JSON = "/home/ubuntu/users/qiuyiwu/aha-art-demo/data/kg_artist_portraits.json"
PORTRAITS_DIR  = "/home/ubuntu/users/qiuyiwu/aha-art-demo/img/portraits"
WV_JSON = "/home/ubuntu/users/qiuyiwu/aha-art-demo/data/kg_worldview_v3.json"
POLES = ["构图","空间","造型","光影","色彩","笔触","边缘"]
POLE_DESC = {"构图":"均衡↔动势","空间":"纵深↔平面","造型":"体积↔消融","光影":"柔和↔强烈",
             "色彩":"沉郁↔明艳","笔触":"隐没↔显露","边缘":"硬朗↔柔化"}

def cfg(p): return json.load(open(os.path.expanduser(p)))
def mimo_cfg():
    m = cfg("~/.aha_mimo.json"); base = m["endpoint"].rstrip("/")
    if not base.endswith("/messages"): base += "/v1/messages"
    return base, m["key"], m["model"]
def parse_json(txt):
    if not txt: return None
    for cand in (txt, *re.findall(r"\{.*\}", txt, re.S)):
        try: return json.loads(cand)
        except Exception: pass
    return None
def call_llm(sysmsg, usermsg, max_tokens=4000, timeout=240):
    base, key, model = mimo_cfg()
    body = json.dumps({"model": model, "max_tokens": max_tokens, "system": sysmsg,
                       "messages": [{"role": "user", "content": usermsg}]}).encode()
    req = urllib.request.Request(base, data=body, method="POST", headers={
        "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    txt = " ".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text").strip()
    return parse_json(txt), txt

def slugify(en, taken):
    base = unicodedata.normalize("NFKD", en or "").encode("ascii","ignore").decode().lower()
    toks = re.findall(r"[a-z0-9]+", base)
    cand = toks[-1] if toks else "x"
    if "ARTIST."+cand not in taken: return "ARTIST."+cand
    cand2 = "".join(toks)
    if "ARTIST."+cand2 not in taken: return "ARTIST."+cand2
    i = 2
    while "ARTIST.%s%d" % (cand, i) in taken: i += 1
    return "ARTIST.%s%d" % (cand, i)

def clamp01(x):
    try: x = float(x)
    except Exception: return None
    return max(0.0, min(1.0, x))

def regions():
    d = json.load(open(WV_JSON))
    return {r["id"]: r for r in d.get("regions", [])}

SYS = """你是 aha 人类美术馆的资深艺术史策展人。aha 用一套"世界观知识图谱 V3"为每位艺术家建立可比较的向量档案。
现在给你一位艺术家的基本信息,请你基于扎实的艺术史知识,起草 TA 的完整 V3 深度档案。

【世界观平面】两根正交轴:X = 再现(0)↔表现(1);Y = 结构(0)↔感知(1)。六个命名区(给出重心坐标供你定位):
WV1 摹写之眼(0.23,0.39)忠实再现/古典写实  WV2 礼制图式(0.41,0.29)程式化/装饰/宗教礼制
WV3 写意寄情(0.53,0.46)东方写意/文人画     WV4 经验之光(0.53,0.73)光感经验/印象
WV5 表现外化(0.78,0.51)强烈主观表现/表现主义 WV6 形式建构(0.82,0.21)抽象/构成/形式实验
请为这位艺术家选最贴切的 region_id,并给出 TA 在平面上的 x,y(0~1,落在该区附近、体现细微差异)。

【七大构成】每项给 0~1 的值(0 偏左极、1 偏右极):
构图 均衡(0)↔动势(1);空间 纵深(0)↔平面(1);造型 体积(0)↔消融(1);光影 柔和(0)↔强烈(1);
色彩 沉郁(0)↔明艳(1);笔触 隐没(0)↔显露(1);边缘 硬朗(0)↔柔化(1)。

【情绪 VAD】v=愉悦度、a=唤起度、d=支配/掌控感,各 0~1,刻画 TA 作品最典型的情绪基调。

只输出一个 JSON(不要任何多余文字、不要 markdown 代码块):
{
 "headline":"一句话定位(≤20字)",
 "bio":"2~3 句生平与艺术贡献",
 "wv":{"region_id":"WV?","region_cn":"区中文名","x":0.0,"y":0.0,"read":"为什么落在这里,≤30字"},
 "styles":["主流派","次流派"],
 "lang":{"构图":0.0,"空间":0.0,"造型":0.0,"光影":0.0,"色彩":0.0,"笔触":0.0,"边缘":0.0},
 "affect":{"v":0.0,"a":0.0,"d":0.0},
 "trajectory":[{"year":"1908","note":"关键节点,≤20字"}],
 "teachers":["老师中文名"],"students":["学生中文名"],"peers":["同侪中文名"],
 "subjects":["人物","肖像","风景"],
 "voice_echo":"TA'为什么而画'的画外音(动机/精神内核,1~2 句)",
 "meaning":"TA 在艺术史上的意义(1 句)",
 "quote":""
}
注意:quote 只填**确有史料记载的真实引文**,拿不准就留空字符串,绝对不要编造。teachers/students/peers 拿不准就给空数组。"""

def draft(basic):
    user = f"""【艺术家基本信息】
中文名:{basic['cn']}
英文名:{basic.get('en') or '—'}
生卒:{basic.get('born') or '?'}–{basic.get('death') or '今'}
国籍:{basic.get('nationality') or '—'}
东西方:{'东方' if basic['region']=='east' else '西方'}
已知流派:{'、'.join(basic.get('styles') or []) or '(请你判断)'}

请按系统要求,为 TA 起草完整 V3 档案,只输出 JSON。"""
    return call_llm(SYS, user)

def build_entry(aid, basic, d, REG):
    wv = d.get("wv") or {}
    rid = wv.get("region_id") if wv.get("region_id") in REG else "WV1"
    cen = REG[rid]
    x = clamp01(wv.get("x")); y = clamp01(wv.get("y"))
    if x is None or y is None:  # LLM 没给合法坐标 → 用区重心 + 确定性微抖动
        j = (len(aid) * 7) % 10 / 10 - 0.5
        x = clamp01(cen["cx"] + j * 0.06); y = clamp01(cen["cy"] + j * 0.06)
    lang = {}
    for k in POLES:
        v = clamp01((d.get("lang") or {}).get(k))
        if v is not None: lang[k] = round(v, 3)
    af = d.get("affect") or {}
    affect = {kk: clamp01(af.get(kk)) for kk in ("v","a","d") if clamp01(af.get(kk)) is not None}
    styles = basic.get("styles") or d.get("styles") or []
    entry = {
        "id": aid, "cn": basic["cn"], "en": basic.get("en"),
        "region": basic["region"], "born": basic.get("born"), "death": basic.get("death"),
        "nationality": basic.get("nationality"),
        "headline": d.get("headline"), "bio": d.get("bio"),
        "wv": {"region_id": rid, "region_cn": cen.get("name") or wv.get("region_cn"),
               "x": round(x,3), "y": round(y,3), "read": wv.get("read")},
        "styles": styles,
        "style_relation": "居于" if styles else None,
        "lang": lang, "affect": affect,
        "trajectory": d.get("trajectory") or [],
        "teachers": d.get("teachers") or [], "students": d.get("students") or [],
        "peers": d.get("peers") or [], "subjects": d.get("subjects") or [],
        "voice_echo": d.get("voice_echo"), "meaning": d.get("meaning"),
        "quote": (d.get("quote") or "").strip(),
        "_added_by": "add_artist.py", "_added_at": time.strftime("%Y-%m-%d"),
    }
    return entry

def show(entry):
    print("\n" + "═"*60)
    print(f"  {entry['cn']}  {entry.get('en') or ''}   [{entry['id']}]")
    print(f"  {entry.get('born') or '?'}–{entry.get('death') or '今'} · {entry.get('nationality') or ''} · {'东方' if entry['region']=='east' else '西方'}")
    print("─"*60)
    print(f"  定位:{entry.get('headline') or '—'}")
    print(f"  世界观:{entry['wv']['region_id']} {entry['wv'].get('region_cn')} (x={entry['wv']['x']}, y={entry['wv']['y']})")
    print(f"         {entry['wv'].get('read') or ''}")
    print(f"  流派:{'、'.join(entry['styles']) or '—'}")
    lang = entry["lang"]
    print("  七大构成:" + ("  ".join(f"{k} {lang[k]}({POLE_DESC[k]})" for k in POLES if k in lang) or "—"))
    af = entry["affect"]
    print(f"  情绪VAD:v={af.get('v')} a={af.get('a')} d={af.get('d')}")
    print(f"  题材:{'、'.join(entry['subjects']) or '—'}")
    print(f"  师/生/侪:{entry['teachers'] or []} / {entry['students'] or []} / {entry['peers'] or []}")
    print(f"  画外音:{entry.get('voice_echo') or '—'}")
    print(f"  意义:{entry.get('meaning') or '—'}")
    print(f"  引文:{entry.get('quote') or '(留空)'}")
    print(f"  生平:{entry.get('bio') or '—'}")
    print("═"*60)

def install_portrait(aid, cn, src_path):
    if not os.path.isfile(src_path):
        print(f"  ⚠ 头像文件不存在,跳过:{src_path}"); return
    os.makedirs(PORTRAITS_DIR, exist_ok=True)
    dst = os.path.join(PORTRAITS_DIR, aid.split(".",1)[1] + ".jpg")
    shutil.copyfile(src_path, dst)
    rel = "img/portraits/" + os.path.basename(dst)
    P = json.load(open(PORTRAITS_JSON)) if os.path.isfile(PORTRAITS_JSON) else {}
    P[aid] = {"file": rel, "source": "手工添加·未核验", "score": 1}
    json.dump(P, open(PORTRAITS_JSON,"w"), ensure_ascii=False, indent=1)
    pub_dir = "/data/pub/p/aha/img/portraits"; os.makedirs(pub_dir, exist_ok=True)
    shutil.copyfile(dst, os.path.join(pub_dir, os.path.basename(dst)))
    shutil.copyfile(PORTRAITS_JSON, "/data/pub/p/aha/data/kg_artist_portraits.json")
    return rel

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cn"); ap.add_argument("--en")
    ap.add_argument("--born", type=int); ap.add_argument("--death", type=int)
    ap.add_argument("--nationality"); ap.add_argument("--region", choices=["east","west"])
    ap.add_argument("--styles", help="逗号分隔")
    ap.add_argument("--id", help="指定 ARTIST.* id,缺省从英文名生成")
    ap.add_argument("--portrait", help="本地头像图片路径,装到 img/portraits/")
    ap.add_argument("--sync", action="store_true", help="写完即跑 ingest_canon_artists.py 灌库")
    ap.add_argument("--yes", action="store_true", help="跳过人工确认")
    a = ap.parse_args()

    def ask(prompt, default=None):
        s = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
        return s or default
    cn = a.cn or ask("中文名(必填)")
    if not cn: sys.exit("× 中文名必填")
    en = a.en or ask("英文名")
    born = a.born or (lambda s: int(s) if s and s.lstrip('-').isdigit() else None)(ask("生年(数字,可空)"))
    death = a.death or (lambda s: int(s) if s and s.lstrip('-').isdigit() else None)(ask("卒年(数字,可空)"))
    nationality = a.nationality or ask("国籍")
    region = a.region or ask("东西方 east/west", "west")
    styles = [s.strip() for s in (a.styles or ask("流派(逗号分隔,可空)") or "").split(",") if s.strip()]
    basic = {"cn":cn,"en":en,"born":born,"death":death,"nationality":nationality,"region":region,"styles":styles}

    data = json.load(open(DEMO_JSON))
    arts = data["artists"]
    if region not in ("east","west"): sys.exit("× region 必须是 east 或 west")
    aid = a.id or slugify(en, set(arts.keys()))
    if aid in arts:
        if not (a.yes or ask(f"⚠ {aid} 已存在,覆盖?(y/N)","N").lower().startswith("y")):
            sys.exit("已取消")

    print(f"\n⏳ 调 mimo 起草 {cn} 的 V3 档案…(约 20~40s)")
    REG = regions()
    d, raw = draft(basic)
    if not d:
        sys.exit("× LLM 未返回可解析 JSON。原始片段:\n" + (raw or "")[:500])
    entry = build_entry(aid, basic, d, REG)
    show(entry)

    if not a.yes:
        if not ask("确认写入?(y/N)","N").lower().startswith("y"):
            print("已取消(未写入任何文件)。"); return

    # 备份 + 写主档 + 部署
    bak = DEMO_JSON + ".bak." + time.strftime("%Y%m%d%H%M%S")
    shutil.copyfile(DEMO_JSON, bak)
    arts[aid] = entry
    if isinstance(data.get("meta",{}).get("n"), int): data["meta"]["n"] = len(arts)
    json.dump(data, open(DEMO_JSON,"w"), ensure_ascii=False, indent=1)
    shutil.copyfile(DEMO_JSON, PUB_JSON)
    print(f"✓ 已写入主档({len(arts)} 位)+ 部署到 docroot;备份 {os.path.basename(bak)}")

    if a.portrait:
        rel = install_portrait(aid, cn, a.portrait)
        if rel:
            entry["portrait"] = rel
            json.dump(data, open(DEMO_JSON,"w"), ensure_ascii=False, indent=1)
            shutil.copyfile(DEMO_JSON, PUB_JSON)
            print(f"✓ 头像已装:{rel}")

    if a.sync:
        print("⏳ 同步进 Postgres…")
        r = subprocess.run([sys.executable, os.path.join(HERE,"ingest_canon_artists.py")],
                           capture_output=True, text=True)
        print(r.stdout.strip() or r.stderr.strip()[:800])
        print("✓ 已灌库。页面立即生效:")
    else:
        print("ℹ 尚未灌库。执行下面这条让页面生效:")
        print(f"   python3 {os.path.join(HERE,'ingest_canon_artists.py')}")
    print(f"   汇总页 https://aha.yishujia.art/kg-artists.html")
    print(f"   详情页 https://aha.yishujia.art/kg-artist.html?id={aid}")
    if not entry.get("portrait"):
        print(f"ℹ 还没头像:把图放好后 --portrait 重跑,或手动加到 kg_artist_portraits.json")

if __name__ == "__main__":
    main()
