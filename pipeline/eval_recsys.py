#!/usr/bin/env python3
"""离线评估台 · T1 —— 用真实事件做「时间留出法」,回答:这套美学推荐到底有没有比 trivial 强?

对每个有足够正反馈的用户:按时间留出最近的若干「正样本作品」(like/collect/dwell),
用剩下的事件重算 μ/d*,然后让各策略对全库候选排序,看留出的目标作品被排到多前。
策略:prod(生产 0.55aha+0.15calm+0.30qual)/ invu(纯倒U)/ nn(最近邻)/ pop(最热)/ rand(随机)。
指标:recall@10、recall@20、MRR(命中名次的倒数均值)。打的是 profile.py 的真实评分函数,不是重写。
"""
import sys, math, hashlib
sys.path.insert(0, '/home/ubuntu/users/qiuyiwu/aha-art/pipeline')
import _profile_aha as P
from _profile_aha import work_vec, dKG, masked_mean, EVENT_W, _clamp

SIGMA = 0.20
AROUSAL_SET = 0.34
TARGET_KINDS = ('like', 'collect', 'dwell')   # 留出的「正样本」来源(强信号)
MIN_POS_WORKS = 4                              # 至少这么多个不同正样本作品才纳入评估
HOLDOUT = 1                                    # 留出最近的几个目标作品


def engaged_rows(cur, uid):
    cur.execute("""
      SELECT e.kind, e.ts, w.work_id, w.vlm
      FROM mu_event e
      JOIN files f ON (e.work_id IS NOT NULL AND f.work_id=e.work_id)
                   OR (e.work_id IS NULL AND f.cos_key=e.target_id)
      JOIN works w ON w.work_id=f.work_id
      WHERE e.uid=%s AND e.kind IN ('open','dwell','like','collect','gen','view','skip')
        AND w.vlm IS NOT NULL
      ORDER BY e.ts ASC""", (uid,))
    rows = []
    for r in cur.fetchall():
        v = work_vec(r["vlm"])
        if v is None:
            continue
        rows.append({"kind": r["kind"], "ts": r["ts"], "wid": r["work_id"],
                     "vec": v, "w": EVENT_W.get(r["kind"], 0)})
    return rows


def mu_dstar(rows):
    pos = [(x["vec"], x["w"]) for x in rows if x["w"] > 0]
    if not pos:
        return None, None
    mu = masked_mean([v for v, _ in pos], [w for _, w in pos])
    ds = [dKG(x["vec"], mu) for x in rows if x["w"] >= 2]
    dstar = _clamp(sum(ds) / len(ds) if ds else 0.30, 0.15, 0.6)
    return mu, dstar


def load_candidates(cur):
    cur.execute("""SELECT w.work_id, w.vlm, w.quality FROM works w
                   WHERE w.status='kept' AND w.vlm->'affect'->'vad' IS NOT NULL""")
    cand = []
    for r in cur.fetchall():
        v = work_vec(r["vlm"])
        if v is None:
            continue
        cand.append({"wid": r["work_id"], "vec": v,
                     "q": float(r["quality"]) if r["quality"] is not None else 0.5})
    return cand


def popularity_tables(cur):
    """返回 (total, by_user):全局 like/collect 热度 + 每用户自己的贡献,用于评估时排除自身(去穿帮)。"""
    cur.execute("""SELECT work_id, uid, count(*) c FROM mu_event
                   WHERE kind IN ('like','collect') AND work_id IS NOT NULL GROUP BY work_id, uid""")
    total, by_user = {}, {}
    for r in cur.fetchall():
        w, u, c = r["work_id"], r["uid"], r["c"]
        total[w] = total.get(w, 0) + c
        by_user.setdefault(u, {})[w] = c
    return total, by_user


def score_one(c, mu, dstar, pop, strat, rng_salt=0, g=0.0):
    v = c["vec"]; wid = c["wid"]
    if strat in ("prod", "invu", "nn", "prod2"):
        d = dKG(v, mu)
    if strat == "prod":
        aha = math.exp(-((d - dstar) ** 2) / (2 * SIGMA * SIGMA))
        ar = v[10] if v[10] is not None else 0.5
        calm = _clamp(1 - abs(ar - AROUSAL_SET))
        return 0.55 * aha + 0.15 * calm + 0.30 * c["q"]
    if strat == "prod2":  # 两极整体切换:冷启动=纯相似(=nn,已证打过随机),成熟=整套旧prod(那个用户命中第1.2)
        sim = 1 - d
        aha = math.exp(-((d - dstar) ** 2) / (2 * SIGMA * SIGMA))
        ar = v[10] if v[10] is not None else 0.5
        calm = _clamp(1 - abs(ar - AROUSAL_SET))
        mature = 0.55 * aha + 0.15 * calm + 0.30 * c["q"]
        return (1 - g) * sim + g * mature
    if strat == "invu":
        return math.exp(-((d - dstar) ** 2) / (2 * SIGMA * SIGMA))
    if strat == "nn":
        return -d
    if strat == "pop":
        return pop.get(wid, 0)
    return int(hashlib.md5(b"%d-%d" % (wid, rng_salt)).hexdigest(), 16) % 100003  # rand


def main():
    import random, statistics, psycopg2.extras
    conn = P._conn(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cand = load_candidates(cur)
    cand_by_id = {c["wid"]: c for c in cand}
    cand_ids = list(cand_by_id.keys())
    pop_total, pop_by_user = popularity_tables(cur)
    cur.execute("SELECT DISTINCT uid FROM mu_event")
    uids = [r["uid"] for r in cur.fetchall()]

    # 标准 LOO + 负采样:每个留出正样本 vs K 个随机负样本(重复 REPEAT 次降方差)
    K = 99; REPEAT = 20
    STRATS = ["prod", "prod2", "invu", "nn", "pop", "rand"]
    agg = {s: {"hit5": [], "hit10": [], "rr": [], "auc": []} for s in STRATS}
    per_user = {s: {} for s in STRATS}
    n_eval = 0

    for uid in uids:
        rows = engaged_rows(cur, uid)
        posw = {}
        for x in rows:
            if x["kind"] in TARGET_KINDS and x["wid"] in cand_by_id:
                posw[x["wid"]] = x["ts"]
        if len(posw) < MIN_POS_WORKS:
            continue
        ordered = sorted(posw.items(), key=lambda kv: kv[1])
        held = [w for w, _ in ordered[-HOLDOUT:]]
        held_set = set(held)
        train = [x for x in rows if x["wid"] not in held_set]
        mu, dstar = mu_dstar(train)
        if mu is None:
            continue
        seen = {x["wid"] for x in rows}                  # 负样本里要排除用户所有看过的
        negpool = [w for w in cand_ids if w not in seen]
        selfc = pop_by_user.get(uid, {})                 # 协同过滤热度:排除当前用户自身贡献(去穿帮)
        pop = {w: pop_total[w] - selfc.get(w, 0) for w in pop_total}
        g = _clamp(sum(1 for x in train if x["w"] > 0) / 20.0)  # 成熟度:正反馈越多 g→1
        n_eval += 1
        urank = {s: [] for s in STRATS}
        for t in held:
            tgt = cand_by_id[t]
            for rep in range(REPEAT):
                rng = random.Random(hash((uid, t, rep)) & 0xffffffff)
                negs = rng.sample(negpool, K)
                arena = [tgt] + [cand_by_id[w] for w in negs]
                for s in STRATS:
                    scored = sorted(arena, key=lambda c: -score_one(c, mu, dstar, pop, s, rep, g))
                    rank = next(i + 1 for i, c in enumerate(scored) if c["wid"] == t)
                    agg[s]["hit5"].append(1.0 if rank <= 5 else 0.0)
                    agg[s]["hit10"].append(1.0 if rank <= 10 else 0.0)
                    agg[s]["rr"].append(1.0 / rank)
                    agg[s]["auc"].append((K + 1 - rank) / K)     # 比目标差的负样本占比
                    urank[s].append(rank)
        for s in STRATS:
            per_user[s][uid[:8]] = round(statistics.mean(urank[s]), 1)

    conn.close()
    print("候选池 %d | 评估用户 %d | 协议:留一法,1 正样本 vs %d 随机负样本 ×%d 次重复\n"
          % (len(cand), n_eval, K, REPEAT))
    if n_eval == 0:
        print("没有用户达到门槛(正样本作品 ≥ %d)。" % MIN_POS_WORKS); return
    NAME = {"prod": "生产foryou-旧(aha+calm+qual)", "prod2": "混合-新(相似+协同+倒U·成熟度门控)",
            "invu": "纯倒U(只aha)", "nn": "最近邻(纯距离)", "pop": "协同(他人like)", "rand": "随机(基准)"}
    print("%-26s  HR@5    HR@10    MRR     AUC   (100路中目标平均名次)" % "策略")
    print("-" * 76)
    for s in STRATS:
        a = agg[s]; mr = statistics.mean([1 / x for x in a["rr"]]) if a["rr"] else 0
        print("%-26s  %.3f   %.3f   %.3f   %.3f      %.1f"
              % (NAME[s], statistics.mean(a["hit5"]), statistics.mean(a["hit10"]),
                 statistics.mean(a["rr"]), statistics.mean(a["auc"]), mr))
    print("\n注:随机基准 HR@10≈0.10、AUC≈0.50。AUC>0.5 = 比随机会把目标排在更多负样本之前。")
    print("\n逐用户 · 各策略下目标的平均名次(共 100,越小越好):")
    print("%-9s | %s" % ("uid", "  ".join("%6s" % s for s in STRATS)))
    for u in per_user["prod"]:
        print("%-9s | %s" % (u, "  ".join("%6.1f" % per_user[s][u] for s in STRATS)))


if __name__ == "__main__":
    main()
