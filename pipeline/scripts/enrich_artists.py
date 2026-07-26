#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量富化/校验策展艺术家库(写 kg_artists.json,末尾统一灌库)。三模式:

  add-missing : 把"被师承/同侪/学生引用、但不在库"的人名补成完整 V3 档案(LLM 据名考据+起草)
  lineage     : 给缺 teachers/students 的艺术家,LLM 起草 师/生/侪(真实或留空)
  verify      : 逐位 LLM 交叉核对(生卒/师承/流派/世界观合理性)→ 写 lore.verify{status,flags,note}

并发跑(ThreadPoolExecutor),幂等。铁律:引文/事实拿不准就标疑点或留空,绝不编造。

用法:
  python3 enrich_artists.py add-missing --min-ref 2 [--limit N] [--dry]
  python3 enrich_artists.py lineage [--limit N] [--dry]
  python3 enrich_artists.py verify  [--limit N] [--dry]
  (默认跑完即 ingest;--no-sync 跳过)
"""
import os, re, sys, json, time, shutil, argparse, threading, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import add_artist as AA   # 复用 mimo_cfg/call_llm/build_entry/regions/slugify/clamp01/POLES

DEMO_JSON = AA.DEMO_JSON; PUB_JSON = AA.PUB_JSON
HERE = os.path.dirname(os.path.abspath(__file__))
_lock = threading.Lock()

# ---------- add-missing ----------
SYS_ADD = """你是 aha 美术馆资深艺术史策展人。给你一个艺术家中文名(可能还有东西方提示),
请据你的艺术史知识考据并起草 TA 的完整 V3 档案。若你不确定此人是否真实存在/无足够史料,把 "uncertain" 设为 true。

世界观平面 X=再现(0)↔表现(1) Y=结构(0)↔感知(1);六区重心:
WV1摹写之眼(.23,.39) WV2礼制图式(.41,.29) WV3写意寄情(.53,.46) WV4经验之光(.53,.73) WV5表现外化(.78,.51) WV6形式建构(.82,.21)
七大构成各0~1:构图 均衡→动势/空间 纵深→平面/造型 体积→消融/光影 柔和→强烈/色彩 沉郁→明艳/笔触 隐没→显露/边缘 硬朗→柔化。
VAD各0~1。

只输出 JSON(无多余文字):
{"uncertain":false,"en":"英文名","born":1832,"death":1883,"nationality":"法国","region":"west|east",
 "headline":"一句话定位","bio":"2~3句","styles":["主流派"],
 "wv":{"region_id":"WV?","region_cn":"区名","x":0.0,"y":0.0,"read":"≤30字"},
 "lang":{"构图":0,"空间":0,"造型":0,"光影":0,"色彩":0,"笔触":0,"边缘":0},
 "affect":{"v":0,"a":0,"d":0},
 "trajectory":[{"year":"1863","note":"≤20字"}],
 "teachers":[],"students":[],"peers":[],"subjects":[],
 "voice_echo":"为什么而画 1~2句","meaning":"艺术史意义 1句","quote":""}
quote 仅填确有记载的真实引文,否则空字符串;拿不准的人名留空数组。"""

def do_add_missing(name, region_hint):
    user = f"艺术家中文名:{name}\n东西方提示:{region_hint or '未知'}\n请考据并起草,只输出 JSON。"
    d, raw = AA.call_llm(SYS_ADD, user, max_tokens=4000)
    if not d or d.get("uncertain"):
        return None
    REG = AA.regions()
    basic = {"cn": name, "en": d.get("en"), "born": d.get("born"), "death": d.get("death"),
             "nationality": d.get("nationality"), "region": d.get("region") if d.get("region") in ("east","west") else (region_hint or "west"),
             "styles": d.get("styles") or []}
    taken = set(json.load(open(DEMO_JSON))["artists"].keys())
    aid = AA.slugify(basic["en"] or name, taken)
    entry = AA.build_entry(aid, basic, d, REG)
    return entry

# ---------- lineage ----------
SYS_LIN = """你是艺术史考据专家。给你一位艺术家,请只回其师承关系(中文名),要确有史料依据,拿不准就给空数组。
只输出 JSON:{"teachers":["老师"],"students":["学生"],"peers":["同侪/同代往来"]}。绝不编造;不确定就空。"""

def do_lineage(a):
    user = f"艺术家:{a.get('cn')}({a.get('en') or ''}),{a.get('born') or '?'}–{a.get('death') or ''},{a.get('nationality') or ''},流派 {('、'.join(a.get('styles') or []))}。\n请给师承,只输出 JSON。"
    d, raw = AA.call_llm(SYS_LIN, user, max_tokens=3000)
    if not d: return None
    out = {}
    for k in ("teachers","students","peers"):
        v = d.get(k)
        if isinstance(v, list) and v:
            out[k] = [str(x).strip() for x in v if str(x).strip()][:8]
    return out or None

# ---------- verify ----------
SYS_VER = """你是严谨的艺术史考据审核员。给你 aha 库里一位艺术家的档案字段,请交叉核对其准确性:
- 生卒年是否正确;国籍/东西方是否对;主流派是否贴切;师承/同侪是否史实;世界观区(WV1摹写写实/WV2礼制装饰/WV3东方写意/WV4光感经验/WV5主观表现/WV6抽象形式)是否与其艺术相符。
输出 JSON:{"status":"verified|疑点|待核","flags":[{"field":"born","issue":"实际1840非1841"}],"note":"一句话总评"}
- verified=各项基本无误;疑点=发现具体错误(写进 flags);待核=信息太少无法判断。
只输出 JSON,基于你的知识,别编造 flag。"""

def do_verify(a):
    fields = {k: a.get(k) for k in ("cn","en","born","death","nationality","region","styles","teachers","students")}
    fields["wv"] = (a.get("wv") or {}).get("region_id"), (a.get("wv") or {}).get("region_cn")
    user = "档案:\n" + json.dumps(fields, ensure_ascii=False) + "\n请核对,只输出 JSON。"
    d, raw = AA.call_llm(SYS_VER, user, max_tokens=3000)
    if not d: return None
    st = d.get("status") if d.get("status") in ("verified","疑点","待核") else "待核"
    return {"status": st, "flags": (d.get("flags") or [])[:6], "note": (d.get("note") or "")[:120],
            "at": time.strftime("%Y-%m-%d")}

# ---------- correct(按疑点做高置信修正,只改结构化硬事实)----------
SYS_COR = """你是顶级艺术史考据专家。给你 aha 库里一位艺术家的档案 + 之前核对发现的疑点。
请只在你**高度确信**的前提下,给出对**结构化硬事实**的修正(其余一律不动):
- wv_region_id:其艺术最符合的世界观区(WV1摹写忠实写实/WV2礼制装饰程式/WV3东方写意文人/WV4光感经验印象/WV5主观强烈表现/WV6抽象形式构成),仅当现值明显错时给出
- born / death:确切生卒年(公元数字),仅当现值错时给出
- region:east 或 west,仅当错时
- nationality:仅当错时
不确定的、需要主观判断的、师承人名这类模糊项,一律不要放进 corrections。
输出 JSON:{"corrections":{"wv_region_id":"WV4","born":1840},"confidence":"high|medium|low","resolved":true,"note":"一句话说改了啥/为何"}
corrections 只含确需修改的字段;没有要改的就给空对象 {}。confidence 反映你对这些修正的把握。"""
WVCN = {'WV1':'摹写之眼','WV2':'礼制图式','WV3':'写意寄情','WV4':'经验之光','WV5':'表现外化','WV6':'形式建构'}
def do_correct(a, REG):
    vf = a.get("verify") or {}
    fields = {k: a.get(k) for k in ("cn","en","born","death","nationality","region","styles")}
    fields["wv_region_id"] = (a.get("wv") or {}).get("region_id")
    user = ("档案:\n" + json.dumps(fields, ensure_ascii=False) +
            "\n之前发现的疑点:\n" + json.dumps(vf.get("flags") or [], ensure_ascii=False) +
            "\n请按系统要求给高置信修正,只输出 JSON。")
    d, raw = AA.call_llm(SYS_COR, user, max_tokens=2500)
    if not d: return None
    cor = d.get("corrections") or {}
    conf = d.get("confidence")
    applied = {}
    if conf == "high" and cor:
        for f in ("born","death"):
            if isinstance(cor.get(f), int) and cor[f] != a.get(f): applied[f] = cor[f]
        if cor.get("region") in ("east","west") and cor["region"] != a.get("region"): applied["region"] = cor["region"]
        if cor.get("nationality") and cor["nationality"] != a.get("nationality"): applied["nationality"] = cor["nationality"]
        rid = cor.get("wv_region_id")
        if rid in REG and rid != (a.get("wv") or {}).get("region_id"):
            applied["wv_region_id"] = rid
    return {"applied": applied, "conf": conf, "resolved": bool(d.get("resolved")), "note": (d.get("note") or "")[:120]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["add-missing","lineage","verify","correct"])
    ap.add_argument("--min-ref", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--no-sync", action="store_true")
    a = ap.parse_args()

    data = json.load(open(DEMO_JSON)); arts = data["artists"]
    canon_cn = set(v.get("cn") for v in arts.values())
    GROUP = re.compile(r'(派|学派|四家|四僧|画院|主义|工坊|工房|兄弟|一脉|流|家族|时期|传统|圈|群|世家|宗|门)$')

    jobs = []  # (key, callable) ; results merged into arts
    if a.mode == "add-missing":
        from collections import Counter
        ref = Counter(); hint = {}
        for v in arts.values():
            for k in ("teachers","students","peers"):
                for nm in (v.get(k) or []):
                    base = re.split(r'[（(]', nm)[0].strip()
                    if base and base not in canon_cn and not GROUP.search(base) and len(base) >= 2:
                        ref[base] += 1; hint.setdefault(base, v.get("region"))
        names = [n for n, c in ref.most_common() if c >= a.min_ref]
        if a.limit: names = names[:a.limit]
        print(f"[add-missing] 待补 {len(names)} 位(≥{a.min_ref}次引用):{names}")
        targets = [(n, lambda n=n: do_add_missing(n, hint.get(n))) for n in names]
    elif a.mode == "lineage":
        miss = [(id, v) for id, v in arts.items() if not (v.get("teachers") or v.get("students"))]
        if a.limit: miss = miss[:a.limit]
        print(f"[lineage] 待补师承 {len(miss)} 位")
        targets = [(id, lambda v=v: do_lineage(v)) for id, v in miss]
    elif a.mode == "correct":
        REG = AA.regions()
        sus = [(id, v) for id, v in arts.items() if (v.get("verify") or {}).get("status") == "疑点" and (v.get("verify") or {}).get("flags")]
        if a.limit: sus = sus[:a.limit]
        print(f"[correct] 待修正疑点 {len(sus)} 位")
        targets = [(id, lambda v=v: do_correct(v, REG)) for id, v in sus]
    else:  # verify
        items = list(arts.items())
        if a.limit: items = items[:a.limit]
        print(f"[verify] 待核 {len(items)} 位")
        targets = [(id, lambda v=v: do_verify(v)) for id, v in items]

    results = {}; fail = 0; done = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        fut = {ex.submit(fn): key for key, fn in targets}
        for f in as_completed(fut):
            key = fut[f]; done += 1
            try: r = f.result()
            except Exception as e: r = None; print("  err", key, str(e)[:80])
            if r is None: fail += 1
            else: results[key] = r
            if done % 10 == 0: print(f"  ...{done}/{len(targets)} (失败{fail})")

    # 合并回 arts
    added = 0; upd = 0
    if a.mode == "add-missing":
        for entry in results.values():
            arts[entry["id"]] = entry; added += 1
        print(f"[add-missing] 成功起草 {added} 位(LLM 判 uncertain/失败 {fail})")
    elif a.mode == "lineage":
        for id, out in results.items():
            arts[id].update(out); upd += 1
        print(f"[lineage] 补了 {upd} 位的师承")
    elif a.mode == "correct":
        REG = AA.regions(); nfix = 0; nfields = 0
        for id, r in results.items():
            ap_ = r.get("applied") or {}
            if ap_:
                a0 = arts[id]; changes = []
                for f in ("born","death","region","nationality"):
                    if f in ap_: changes.append(f"{f}:{a0.get(f)}→{ap_[f]}"); a0[f] = ap_[f]; nfields += 1
                if "wv_region_id" in ap_:
                    rid = ap_["wv_region_id"]; cen = REG[rid]
                    old = (a0.get("wv") or {}).get("region_id")
                    a0.setdefault("wv", {}); a0["wv"]["region_id"] = rid; a0["wv"]["region_cn"] = cen.get("name") or WVCN.get(rid)
                    a0["wv"]["x"] = round(cen["cx"], 3); a0["wv"]["y"] = round(cen["cy"], 3)
                    changes.append(f"wv:{old}→{rid}"); nfields += 1
                nfix += 1
                a0["verify"] = {"status": "verified" if r.get("resolved") and r.get("conf") == "high" else "疑点",
                                "flags": [] if r.get("resolved") else (a0.get("verify") or {}).get("flags", []),
                                "note": "已按考据修正:" + ";".join(changes), "at": time.strftime("%Y-%m-%d"),
                                "corrected": changes}
        print(f"[correct] 应用高置信修正 {nfix} 位 / 共 {nfields} 处字段;其余疑点保留待人工")
        upd = nfix
    else:
        for id, v in results.items():
            arts[id]["verify"] = v; upd += 1
        from collections import Counter
        c = Counter(v["status"] for v in results.values())
        print(f"[verify] 核了 {upd} 位:{dict(c)}")

    if a.dry:
        print("DRY — 不写盘。样例:", json.dumps(list(results.items())[:1], ensure_ascii=False)[:600]); return

    bak = DEMO_JSON + ".bak." + time.strftime("%Y%m%d%H%M%S")
    shutil.copyfile(DEMO_JSON, bak)
    if isinstance(data.get("meta", {}).get("n"), int): data["meta"]["n"] = len(arts)
    json.dump(data, open(DEMO_JSON, "w"), ensure_ascii=False, indent=1)
    shutil.copyfile(DEMO_JSON, PUB_JSON)
    print(f"✓ 写入主档({len(arts)} 位)+ 部署;备份 {os.path.basename(bak)}")
    if not a.no_sync:
        r = subprocess.run([sys.executable, os.path.join(HERE, "ingest_canon_artists.py")], capture_output=True, text=True)
        print(r.stdout.strip()[-400:] or r.stderr.strip()[-400:])

if __name__ == "__main__":
    main()
