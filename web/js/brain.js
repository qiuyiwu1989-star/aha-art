// ═══ L3 · 智能层 / Match API  ——  V0.3「美学奖励」内核 ═══
// 依赖 L1(Content),从不被反向依赖。
//
// V0.2 → V0.3 的灵魂跃迁:从「相似度最大化」→「顿悟期望最大化」。
// 奖励函数(显式建模审美体验,而非停留时长):
//   E[reward] = α·Aha + γ·Calm + δ·Info + β·Growth − λ·冗余 − μ·疲劳
//     · Aha 顿悟   = 倒U(到你口味的距离, 个性化惊奇带 d*) × 可消解性(锚/桥)
//     · Calm 安静  = arousal 贴近低设定点 + 轨迹平滑(惩罚 jerk)
//     · Info 信息  = 不确定性驱动的探索(越不懂你的维度越想问)
//     · Growth 成长= 向"已掌握区的相邻未探索区"扩张(前沿/课程)
//   + dwell 金标签、三时间尺度、三盏奖励灯(顿悟密度/审美成长/安静感)、report()
//   + KG 深层空间(styleVec/worldModel/voice)优先,现数据(color/mood/theme)降级
import { Content } from './content.js';

const LS = 'aha.taste.v3';
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const round = (x, n = 3) => +(+x).toFixed(n);
const ema = (o, n, r) => o == null ? n : o + (n - o) * r;
function emaHSL(old, nw, r) {
  if (!old) return nw.slice();
  const a = old[0] * Math.PI / 180, b = nw[0] * Math.PI / 180;
  const x = (1 - r) * Math.cos(a) + r * Math.cos(b), y = (1 - r) * Math.sin(a) + r * Math.sin(b);
  let h = Math.atan2(y, x) * 180 / Math.PI; if (h < 0) h += 360;
  return [h, ema(old[1], nw[1], r), ema(old[2], nw[2], r)];
}
const hueDist = (h1, h2) => { let d = Math.abs(h1 - h2); return Math.min(d, 360 - d) / 180; };
function jaccard(a = [], b = []) { if (!a.length || !b.length) return 0; const B = new Set(b); let i = 0; a.forEach(t => B.has(t) && i++); return i / (a.length + b.length - i); }

// ── 审美 4 维特征(KG 缺位时的深层空间代理,也是报告坐标)──
//   light 明↔暗 · warm 冷↔暖 · energy 静↔动 · modern 古↔今
function feat(w) {
  if (!w.color || !w.mood) return null;
  const [h, s, l] = w.color.hsl;
  const warmHue = 0.5 + 0.5 * Math.cos((h - 40) * Math.PI / 180); // 红橙黄=暖
  return [
    l,
    clamp(0.5 * (warmHue * (0.35 + 0.65 * s)) + 0.5 * (w.mood.valence ?? 0.5)),
    w.mood.arousal ?? 0.4,
    clamp(((w.century ?? 18) - 15) / 6),
  ];
}
const featDist = (a, b) => { let s = 0; for (let i = 0; i < 4; i++) s += (a[i] - b[i]) ** 2; return Math.sqrt(s) / 2; }; // 0..1
const AXIS_LABEL = ['明↔暗', '冷↔暖', '静↔动', '古↔今'];
function colorSim(c, k) { if (!c || !k) return 0; const sat = Math.min(c[1], k[1]); const dh = hueDist(c[0], k[0]) * (0.3 + 0.7 * sat); return clamp(1 - Math.sqrt(0.5 * dh * dh + 0.2 * (c[1] - k[1]) ** 2 + 0.3 * (c[2] - k[2]) ** 2)); }
function moodSim(m, k) { if (!m || !k) return 0; return clamp(1 - Math.sqrt(((m.valence ?? 0) - k.valence) ** 2 + ((m.arousal ?? 0) - k.arousal) ** 2) / Math.SQRT2); }
function workSim(a, b) { const c = a.color && b.color ? colorSim(a.color.hsl, b.color.hsl) : 0; const m = a.mood && b.mood ? moodSim(a.mood, b.mood) : 0; return 0.4 * c + 0.3 * m + 0.3 * jaccard(a.themes, b.themes); }
function styleVecSim(a, b) { if (!a || !b) return 0; let d = 0, na = 0, nb = 0; for (let i = 0; i < a.length; i++) { d += a[i] * b[i]; na += a[i] ** 2; nb += b[i] ** 2; } return na && nb ? clamp((d / Math.sqrt(na * nb) + 1) / 2) : 0; }

function freshProfile() {
  return {
    themes: {}, color: null, mood: null, era: null,
    loved: [],                              // [{id,w}] 心动集(多峰 kNN + 锚)
    fz: { sum: [0, 0, 0, 0], n: 0 },        // 审美特征质心累加(均值)
    fvar: [0, 0, 0, 0],                     // 各维方差估计(不确定性)
    seenThemes: {},                         // 已见母题分布(成长/前沿)
    wm: {}, voice: {},                      // KG:世界模型/画外音分布(预留)
    exploreAppetite: 0.25, n: 0, updatedAt: 0,
  };
}

export const Brain = {
  version: '0.3',

  // 奖励项权重(arch / lab 面板滑块直接改)
  weights: { aha: 1.0, calm: 0.6, info: 0.5, growth: 0.35, diversity: 0.3, fatigue: 0.45 },
  // 美学超参:个性化惊奇带、安静设定点
  params: { dStar: 0.42, sigma: 0.22, arousalSet: 0.34 },

  profile: (() => { try { return Object.assign(freshProfile(), JSON.parse(localStorage.getItem(LS) || '{}')); } catch { return freshProfile(); } })(),
  session: { color: null, mood: null, recent: [] },
  served: [],                               // 服务序列的 arousal(算 Calm 轨迹)
  meters: { epiphany: 0, growth: 0, calm: 1, _ep: 0, _int: 0 },  // 三盏奖励灯
  log: [], lastDecision: null, lastCalls: [], lastFunnel: null,

  _save() { try { localStorage.setItem(LS, JSON.stringify(this.profile)); } catch {} },
  reset() { this.profile = freshProfile(); this.session = { color: null, mood: null, recent: [] }; this.served = []; this.meters = { epiphany: 0, growth: 0, calm: 1, _ep: 0, _int: 0 }; this._probed = [0, 0, 0, 0]; this.log = []; this.lastFunnel = null; this._save(); },

  // 个性化惊奇带:好奇胃口越大峰越靠后;当下越想静,峰越靠前(更温和)
  _dStar() {
    const calmNow = this.session.mood ? clamp(1 - this.session.mood.arousal) : 0.5;
    return clamp(this.params.dStar + 0.32 * (this.profile.exploreAppetite - 0.25) - 0.12 * (calmNow - 0.5), 0.15, 0.75);
  },
  _centroid(space) { const L = this.profile[space], S = this.session[space], k = 0.35; if (!L) return S; if (!S) return L; return space === 'color' ? emaHSL(L, S, k) : { valence: ema(L.valence, S.valence, k), arousal: ema(L.arousal, S.arousal, k) }; },
  _centroidFeat() { const z = this.profile.fz; return z.n ? z.sum.map(s => s / z.n) : null; },
  _uncertainty() { const z = this.profile.fz; const cnt = clamp(1 / (1 + z.n / 4)); const v = clamp(this.profile.fvar.reduce((a, b) => a + b, 0) / 4 * 4); return clamp(0.6 * cnt + 0.4 * v); },

  topThemes(n = 6) { return Object.entries(this.profile.themes).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, n); },
  matched(work, k = 2) { const top = this.topThemes(8).map(x => x[0]); return (work.themes || []).filter(t => top.includes(t)).slice(0, k); },

  // 全局新异度 d(在审美深层空间);有 KG 风格轴则优先用风格轴
  _novelty(work) {
    if (work.styleVec && this.profile.styleVec) return clamp(1 - styleVecSim(work.styleVec, this.profile.styleVec));
    const cf = this._centroidFeat(), fv = feat(work);
    if (!cf || !fv) return 0.5;
    return featDist(fv, cf);
  },
  // 可消解性(锚/桥):全局新异、但有一条强把手(图谱边到心动集 / 某一轴很贴)
  _anchor(work) {
    const fv = feat(work), cf = this._centroidFeat();
    let axisClose = 0;
    if (fv && cf) for (let i = 0; i < 4; i++) axisClose = Math.max(axisClose, 1 - Math.abs(fv[i] - cf[i]));
    let bridge = 0;
    const lovedIds = new Set(this.profile.loved.map(l => l.id));
    if (lovedIds.size) { const ns = Content.neighbors(work.slug); if (ns.some(n => lovedIds.has(n.to))) bridge = 1; }
    // KG 把手:同世界模型 / 同画外音 = 强锚(数据到了才生效)
    const domWM = Object.entries(this.profile.wm).sort((a, b) => b[1] - a[1])[0];
    if (work.worldModel && domWM && work.worldModel === domWM[0]) bridge = Math.max(bridge, 0.8);
    return clamp(0.55 * axisClose + 0.45 * bridge);
  },

  // ── 打分 = 美学奖励(返回 total + 分项,供面板/报告)──
  scoreBreakdown(work) {
    const W = this.weights, P = this.params, parts = {};
    const d = this._novelty(work);
    const dStar = this._dStar();
    const aha = Math.exp(-((d - dStar) ** 2) / (2 * P.sigma * P.sigma)) * (0.4 + 0.6 * this._anchor(work));
    const en = work.mood ? (work.mood.arousal ?? 0.4) : 0.4;
    const last = this.served.length ? this.served[this.served.length - 1] : en;
    const calm = clamp((1 - Math.abs(en - P.arousalSet)) - 0.5 * Math.abs(en - last));
    const info = clamp(this._uncertainty() * (0.3 + 0.7 * d));
    // 成长:未见母题占比 + 时代新异
    const th = work.themes || [];
    const newTh = th.length ? th.filter(t => !this.profile.seenThemes[t]).length / th.length : 0;
    const eraNov = this.profile.era != null && work.century != null ? clamp(Math.abs((work.century - 15) / 6 - (this.profile.era - 15) / 6)) : 0.5;
    const wmNew = work.worldModel && !this.profile.wm[work.worldModel] ? 1 : 0;   // KG:没去过的世界模型 = 成长
    const growth = clamp(0.5 * newTh + 0.3 * eraNov + 0.2 * wmNew);

    parts.aha = round(aha); parts.calm = round(calm); parts.info = round(info); parts.growth = round(growth);
    parts.d = round(d);  // 给面板看"它离你多远"
    const total = (W.aha * aha + W.calm * calm + W.info * info + W.growth * growth) / (W.aha + W.calm + W.info + W.growth || 1);
    return { total: round(total), parts };
  },
  score(work) { return this.scoreBreakdown(work).total; },

  // ── L2 → L3:收信号、更新画像 + 奖励灯 ───────────────
  ingest(sig) {
    const w = Content.getWork(sig.workId);
    const base = { heart: 2, choose: 2, door: 1, view: 0.3, skip: -0.5, reject: -0.6, dwell: 0 };
    let weight = base[sig.type] ?? 0;
    if (sig.type === 'dwell') weight = round(clamp(0.012 * (sig.value || 0), 0, 1.6)); // dwell 金标签:凝视越久越正

    if (w) {
      (w.themes || []).forEach(t => { this.profile.themes[t] = round((this.profile.themes[t] || 0) + weight, 2); this.profile.seenThemes[t] = (this.profile.seenThemes[t] || 0) + 1; });
      const noveltyNow = this._novelty(w);
      if (weight > 0) {
        const r = clamp(0.15 * weight, 0.05, 0.5);
        if (w.color) { this.profile.color = emaHSL(this.profile.color, w.color.hsl, r); this.session.color = emaHSL(this.session.color, w.color.hsl, 0.45); }
        if (w.mood) {
          this.profile.mood = this.profile.mood ? { valence: ema(this.profile.mood.valence, w.mood.valence, r), arousal: ema(this.profile.mood.arousal, w.mood.arousal, r) } : { ...w.mood };
          this.session.mood = this.session.mood ? { valence: ema(this.session.mood.valence, w.mood.valence, 0.45), arousal: ema(this.session.mood.arousal, w.mood.arousal, 0.45) } : { ...w.mood };
        }
        if (w.century != null) this.profile.era = ema(this.profile.era, w.century, r);
        // 审美特征质心 + 方差(在线)
        const fv = feat(w);
        if (fv) { const z = this.profile.fz, old = z.n ? z.sum.map(s => s / z.n) : fv; z.n++; for (let i = 0; i < 4; i++) { z.sum[i] += fv[i]; const mean = z.sum[i] / z.n; this.profile.fvar[i] = ema(this.profile.fvar[i], (fv[i] - old[i]) * (fv[i] - mean), 0.3); } }
        if (w.worldModel) this.profile.wm[w.worldModel] = (this.profile.wm[w.worldModel] || 0) + weight;
        if (w.voice) this.profile.voice[w.voice] = (this.profile.voice[w.voice] || 0) + weight;
        if (w.styleVec) this.profile.styleVec = this.profile.styleVec ? this.profile.styleVec.map((x, i) => ema(x, w.styleVec[i], r)) : w.styleVec.slice();  // KG:风格轴质心
        if (sig.type === 'heart' || sig.type === 'choose') { this.profile.loved.unshift({ id: w.slug, w: weight }); this.profile.loved = this.profile.loved.slice(0, 12); }
        this.profile.n++;
      }
      // 奖励灯:顿悟 = 对"新异"项的强正反应
      if (sig.type === 'heart' || sig.type === 'choose' || (sig.type === 'dwell' && weight > 0.6)) {
        this.meters._int++; if (noveltyNow > this._dStar() - this.params.sigma) this.meters._ep++;
      } else if (sig.type === 'skip' || sig.type === 'view') this.meters._int++;
      this.session.recent = [...(w.themes || []), ...this.session.recent].slice(0, 8);
    }
    this.profile.updatedAt = (sig.context && sig.context.ts) || this.profile.updatedAt;
    this._refreshMeters();
    this._save();
    const entry = { type: sig.type, workId: sig.workId, title: w && w.title, weight, themes: w ? w.themes : [] };
    this.log.unshift(entry); this.log = this.log.slice(0, 14);
    return entry;
  },

  _refreshMeters() {
    this.meters.epiphany = this.meters._int ? clamp(this.meters._ep / this.meters._int) : 0;
    // 成长 = 已见母题分布的归一化熵 + 口味确定度
    const counts = Object.values(this.profile.seenThemes); const tot = counts.reduce((a, b) => a + b, 0);
    let H = 0; if (tot) counts.forEach(c => { const p = c / tot; H -= p * Math.log(p); });
    const Hn = counts.length > 1 ? H / Math.log(counts.length) : 0;
    this.meters.growth = clamp(0.6 * Hn + 0.4 * (1 - this._uncertainty()));
    // 安静 = 序列 arousal 贴设定点 + 平滑(低 jerk)
    const s = this.served; if (s.length) {
      const meanA = s.reduce((a, b) => a + b, 0) / s.length;
      let jerk = 0; for (let i = 1; i < s.length; i++) jerk += Math.abs(s[i] - s[i - 1]); jerk = s.length > 1 ? jerk / (s.length - 1) : 0;
      this.meters.calm = clamp(1 - 0.7 * Math.abs(meanA - this.params.arousalSet) - 0.8 * jerk);
    }
  },

  _recall(exclude) {
    const pool = Content.all().filter(w => !exclude.has(w.slug));
    const chans = [], cCol = this._centroid('color'), cMood = this._centroid('mood');
    if (this.profile.n === 0) {
      chans.push({ name: 'seed', label: '冷启动·多样种子', ids: [...pool].sort((a, b) => (b.themes || []).length - (a.themes || []).length).slice(0, 14).map(w => w.slug) });
    } else {
      if (cCol || cMood) chans.push({ name: 'visual', label: '风格/视觉近邻', ids: [...pool].map(w => ({ w, s: 0.5 * (w.color ? colorSim(w.color.hsl, cCol) : 0) + 0.5 * (w.mood ? moodSim(w.mood, cMood) : 0) })).sort((a, b) => b.s - a.s).slice(0, 16).map(x => x.w.slug) });
      const gids = []; this.profile.loved.slice(0, 3).forEach(l => Content.neighbors(l.id).forEach(n => { if (!exclude.has(n.to)) gids.push(n.to); }));
      if (gids.length) chans.push({ name: 'graph', label: '图谱·桥', ids: [...new Set(gids)].slice(0, 12) });
      const tt = this.topThemes(1)[0];
      if (tt) chans.push({ name: 'theme', label: `同母题 #${tt[0]}`, ids: Content.byTheme(tt[0]).filter(w => !exclude.has(w.slug)).slice(0, 10).map(w => w.slug) });
      // 惊奇带召回:在审美空间里"中等距离"的一撮(倒U弹药)
      const cf = this._centroidFeat();
      if (cf) { const dS = this._dStar(); chans.push({ name: 'surprise', label: '惊奇带 d*', ids: [...pool].map(w => { const fv = feat(w); return { w, e: fv ? Math.abs(featDist(fv, cf) - dS) : 9 }; }).sort((a, b) => a.e - b.e).slice(0, 12).map(x => x.w.slug) }); }
    }
    const ids = new Set(); chans.forEach(c => c.ids.forEach(id => ids.add(id)));
    return { chans, pool: [...ids].map(id => Content.getWork(id)).filter(Boolean) };
  },

  _rerank(ranked) {
    const W = this.weights, out = [], picked = [], pool = ranked.slice();
    while (pool.length && out.length < 8) {
      let bi = -1, bv = -Infinity;
      pool.forEach((c, i) => {
        const w = Content.getWork(c.id);
        const div = picked.length ? Math.max(...picked.map(p => workSim(w, p))) : 0;
        const fatigue = (w.themes || []).length ? w.themes.filter(t => this.session.recent.includes(t)).length / w.themes.length : 0;
        const v = c.score - W.diversity * div - W.fatigue * fatigue;
        if (v > bv) { bv = v; bi = i; }
      });
      const c = pool.splice(bi, 1)[0]; c.rerank = round(bv); out.push(c); picked.push(Content.getWork(c.id));
    }
    return out;
  },

  _reason(work, parts, isExplore) {
    if (isExplore) return '踮脚一张 · 沿一条轴走出舒适区';
    if (this.profile.n === 0) return '起点 · 先给你多样的一帧';
    const m = this.matched(work);
    const best = Object.entries(parts).filter(([k]) => ['aha', 'calm', 'info', 'growth'].includes(k)).sort((a, b) => b[1] - a[1])[0];
    const lab = { aha: '正落在你的"惊奇甜点"上(意外但接得住)', calm: '与此刻的安静同频', info: '一次试探 · 想更懂你', growth: '带你往没去过的审美邻域走一步' };
    return (best ? lab[best[0]] : '为你而来') + (m.length ? ` · #${m[0]}` : '');
  },

  nextFor({ exclude = [] } = {}) {
    const ex = new Set(exclude);
    let { chans, pool } = this._recall(ex);
    if (!pool.length && ex.size) { ex.clear(); ({ chans, pool } = this._recall(ex)); }   // 看完一轮:清空已看重来
    this.lastCalls = ['Content.all()', ...chans.map(c => `recall:${c.name} → ${c.ids.length}`)];
    if (!pool.length) { this.lastFunnel = { channels: [], poolN: 0, ranked: [], reranked: [], chosenId: null, reason: '暂无候选' }; this.lastDecision = { kind: 'next', candidates: [], chosenId: null, reason: '暂无候选' }; return this.lastDecision; }
    let ranked = pool.map(w => { const b = this.scoreBreakdown(w); return { id: w.slug, title: w.title, artist: w.artist, score: b.total, parts: b.parts, channels: chans.filter(c => c.ids.includes(w.slug)).map(c => c.name) }; }).sort((a, b) => b.score - a.score);
    const reranked = this._rerank(ranked);
    let chosen = reranked[0];
    if (reranked.length > 3 && Math.random() < this.profile.exploreAppetite) { chosen = reranked[reranked.length - 1]; chosen.explore = true; }
    chosen.chosen = true;
    const work = Content.getWork(chosen.id);
    // 记录服务序列(算 Calm 轨迹)
    if (work.mood) { this.served.push(work.mood.arousal ?? 0.4); this.served = this.served.slice(-20); this._refreshMeters(); }
    const reason = this._reason(work, chosen.parts, chosen.explore);
    this.lastFunnel = { channels: chans.map(c => ({ label: c.label, n: c.ids.length })), poolN: pool.length, ranked: ranked.slice(0, 6), reranked: reranked.map(r => ({ id: r.id, title: r.title, rerank: r.rerank, score: r.score, chosen: r.id === chosen.id, explore: !!r.explore })), chosenId: chosen.id, reason };
    this.lastDecision = { kind: 'next', candidates: reranked.map(r => ({ id: r.id, title: r.title, score: r.score, explore: !!r.explore, chosen: r.id === chosen.id })), chosenId: chosen.id, reason };
    return this.lastDecision;
  },

  rankNeighbors(id, fromId = null) {
    const ns = Content.neighbors(id).filter(n => n.to !== fromId);
    this.lastCalls = [`Content.neighbors('${id}') → ${ns.length}`];
    let list = ns.map(n => { const w = Content.getWork(n.to); return { to: n.to, type: n.type, why: n.why, title: w.title, score: this.score(w) }; }).sort((a, b) => b.score - a.score);
    if (list.length > 3) list[list.length - 1].explore = true;
    return list;
  },

  // ══ 测量模式(测评/校准):最大化信息 + 覆盖,而非取悦 ══
  // 语料各轴的离散度(知道哪条轴"测得动")
  _corpusSpread() {
    if (this._spread) return this._spread;
    const fs = Content.all().map(feat).filter(Boolean), sp = [0, 0, 0, 0];
    for (let i = 0; i < 4; i++) { const v = fs.map(f => f[i]); const m = v.reduce((a, b) => a + b, 0) / v.length; sp[i] = Math.sqrt(v.reduce((a, b) => a + (b - m) ** 2, 0) / v.length); }
    this._spread = sp; return sp;
  },
  // 当前最该问的轴 = 不确定 × 可测(语料铺得开)× 轮换(别老问同一条)
  _targetAxis() {
    const sp = this._corpusSpread(), z = this.profile.fz; if (!this._probed) this._probed = [0, 0, 0, 0];
    let bi = 0, bv = -1;
    for (let i = 0; i < 4; i++) { const unc = z.n ? clamp(this.profile.fvar[i] * 4) : 1; const s = (0.45 + 0.55 * unc) * sp[i] / (1 + this._probed[i] * 0.5); if (s > bv) { bv = s; bi = i; } }
    return bi;
  },
  _markProbed(label) { const i = AXIS_LABEL.indexOf(label); if (i >= 0) { if (!this._probed) this._probed = [0, 0, 0, 0]; this._probed[i]++; } },
  // 自适应选下一张(测评单图):覆盖(离已看远)+ 在目标轴上试探
  probe({ seen = [], pool = null } = {}) {
    const ex = new Set(seen);
    let cands = (pool ? pool.map(id => Content.getWork(id)) : Content.all()).filter(w => w && !ex.has(w.slug) && feat(w));
    if (!cands.length) cands = Content.all().filter(w => !ex.has(w.slug) && feat(w));
    if (!cands.length) return null;
    const ax = this._targetAxis(), cf = this._centroidFeat();
    const seenF = [...ex].map(id => Content.getWork(id)).filter(Boolean).map(feat).filter(Boolean);
    let best = null, bv = -1;
    for (const w of cands) { const f = feat(w); const cov = seenF.length ? Math.min(...seenF.map(s => featDist(f, s))) : 1; const probe = cf ? Math.abs(f[ax] - cf[ax]) : 1; const s = 0.6 * cov + 0.4 * probe; if (s > bv) { bv = s; best = w; } }
    this.lastProbeAxis = AXIS_LABEL[ax]; this._markProbed(AXIS_LABEL[ax]);
    return { id: best.slug, axis: AXIS_LABEL[ax] };
  },
  // 自适应二选一:在目标轴上拉开、其它轴接近 → 隔离该轴
  probePair({ seen = [] } = {}) {
    const ex = new Set(seen), cands = Content.all().filter(w => !ex.has(w.slug) && feat(w));
    if (cands.length < 2) return null;
    const ax = this._targetAxis(); let pair = null, bv = -1;
    for (let i = 0; i < cands.length; i++) for (let j = i + 1; j < cands.length; j++) {
      const a = feat(cands[i]), b = feat(cands[j]); const sep = Math.abs(a[ax] - b[ax]); let other = 0; for (let k = 0; k < 4; k++) if (k !== ax) other += Math.abs(a[k] - b[k]);
      const s = 1.5 * sep - other; if (s > bv) { bv = s; pair = [cands[i], cands[j]]; }
    }
    if (!pair) return null;
    this._markProbed(AXIS_LABEL[ax]);
    const [lo, hi] = feat(pair[0])[ax] < feat(pair[1])[ax] ? pair : [pair[1], pair[0]];
    return { axis: AXIS_LABEL[ax], low: lo.slug, high: hi.slug };
  },
  measured() { return clamp(1 - this._uncertainty()); },   // 口味清晰度(测到清楚为止用)

  // ── 美学评估报告 ───────────────────────────────────
  report() {
    const cf = this._centroidFeat() || [0.5, 0.5, 0.4, 0.5];
    const axes = [
      { key: 'light', l: '暗', r: '明', v: cf[0] },
      { key: 'warm', l: '冷', r: '暖', v: cf[1] },
      { key: 'energy', l: '静', r: '动', v: cf[2] },
      { key: 'modern', l: '古典', r: '现代', v: cf[3] },
    ];
    const themes = this.topThemes(6).map(([t, v]) => ({ t, v }));
    const color = this.profile.color ? `hsl(${Math.round(this.profile.color[0])},${Math.round(this.profile.color[1] * 70 + 10)}%,${Math.round(this.profile.color[2] * 100)}%)` : '#999';
    const loved = this.profile.loved.map(l => Content.getWork(l.id)).filter(Boolean);
    const conf = clamp(1 - this._uncertainty());
    const persona = this._persona(cf, themes);
    // KG 真标注到位后才有:风格 4 轴 / 世界模型 / 画外音
    const sv = this.profile.styleVec;
    const styleAxes = sv ? [['再现', '表现'], ['结构', '感知'], ['秩序', '张力'], ['节制', '强度']].map((p, i) => ({ l: p[0], r: p[1], v: clamp((sv[i] + 1) / 2) })) : null;
    const worldModel = Object.entries(this.profile.wm).sort((a, b) => b[1] - a[1])[0]?.[0] || null;
    const voice = Object.entries(this.profile.voice).sort((a, b) => b[1] - a[1])[0]?.[0] || null;
    return {
      n: this.profile.n, axes, styleAxes, worldModel, voice, themes, color, loved, confidence: round(conf),
      exploreAppetite: this.profile.exploreAppetite,
      mood: this.profile.mood, era: this.profile.era,
      meters: { epiphany: round(this.meters.epiphany), growth: round(this.meters.growth), calm: round(this.meters.calm) },
      archetype: persona.archetype, blurb: persona.blurb,
    };
  },
  _persona(cf, themes) {
    const [light, warm, energy, modern] = cf;
    const dark = light < 0.42, bright = light > 0.6, still = energy < 0.42, lively = energy > 0.56;
    const classic = modern < 0.4, contemp = modern > 0.62, w = warm > 0.55;
    let archetype = '安静的观看者';
    if (still && dark) archetype = '在幽暗中寻光的人';
    else if (still && bright) archetype = '澄明的栖居者';
    else if (lively && w) archetype = '热烈的感受者';
    else if (lively) archetype = '逐流动的眼睛';
    else if (classic) archetype = '古典的灵魂';
    else if (contemp) archetype = '当代的漫游者';
    const topT = themes[0] ? themes[0].t : null;
    const parts = [];
    parts.push(dark ? '你被低光与幽暗里的层次吸引' : bright ? '你亲近明亮、透气的画面' : '你在明暗之间取一种平衡');
    parts.push(still ? '偏爱安静、沉缓、可以久看的画面' : lively ? '偏爱有动势、有呼吸感的画面' : '动静皆可,看心情');
    parts.push(w ? '色调上更靠暖' : '色调上偏冷、偏克制');
    parts.push(classic ? '时间上更眷恋古典与近代' : contemp ? '时间上更向近现代倾斜' : '横跨古今');
    if (topT) parts.push(`「${topT}」是反复打动你的母题`);
    const tail = this.profile.exploreAppetite > 0.35 ? '你愿意被惊到——给你一点意外,你会更亮。' : '你享受熟悉中的细腻共鸣,惊喜要轻轻地来。';
    return { archetype, blurb: parts.join(',') + '。' + tail };
  },
};
