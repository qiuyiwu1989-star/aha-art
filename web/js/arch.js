// ═══ L2 · 一个最小逛法 + 架构活体面板(让三层可见)═══
import { Content } from './content.js';
import { Brain } from './brain.js';

const $ = s => document.querySelector(s);
const esc = s => String(s || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let cur = null, fromId = null, seen = new Set(), lastDoors = [];

function imgEl(w) {
  const d = document.createElement('div'); d.className = 'a-art';
  d.innerHTML = `<img class="blur" src="${w.lqip || ''}" aria-hidden="true"/><img class="full" alt=""/><div class="fb">《${esc(w.title)}》<br/><span>${esc(w.artist || '')}</span></div>`;
  const f = d.querySelector('.full'); let r = 0;
  f.onload = () => f.classList.add('on');
  f.onerror = () => { if (!r && /\/\d+,\//.test(w.image)) { r = 1; f.src = w.image.replace(/\/\d+,\//, '/600,/'); } else d.classList.add('failed'); };
  f.src = w.image; return d;
}
function renderWork(w) {
  const h = $('#artHolder'); h.innerHTML = ''; h.appendChild(imgEl(w));
  $('#wTitle').innerHTML = `《${esc(w.title)}》 <span class="wby">${esc(w.artist || '')} · ${esc(w.date || '')}</span>`;
  $('#wThemes').innerHTML = (w.themes || []).map(t => `<span class="thm">#${esc(t)}</span>`).join('');
}
function renderDoors(doors) {
  $('#doors').innerHTML = doors.map((d, i) => `<button class="door ${d.explore ? 'exp' : ''}" data-to="${d.to}">
    <span class="dc">${d.explore ? '探索✦' : esc(Content.typeLabel(d.type))} · 匹配分 ${d.score}</span>${esc(d.why)}</button>`).join('');
  $('#doors').querySelectorAll('.door').forEach(b => b.onclick = () => act('door', { to: b.dataset.to }));
}

function flashFlow() {
  ['#cardL2', '#cardL3', '#cardL1'].forEach((id, i) => setTimeout(() => {
    const el = $(id); el.classList.add('flash'); setTimeout(() => el.classList.remove('flash'), 520);
  }, i * 200));
}

function act(type, payload = {}) {
  const calls = [];
  // 1) L2 发信号 → L3 ingest
  let sigWork = type === 'door' ? payload.to : cur;
  let entry = null;
  if (type !== 'start') entry = Brain.ingest({ type, workId: sigWork, mode: 'arch', context: { ts: Date.now() } });
  // 2) 决策:门=跟随;心动/跳过=画来找你
  let decision, nextId;
  if (type === 'door') {
    decision = { kind: 'door', candidates: lastDoors.map(d => ({ id: d.to, title: d.title, score: d.score, explore: d.explore, chosen: d.to === payload.to })), chosenId: payload.to, reason: '你推开了这扇门(沿图谱前进)' };
    nextId = payload.to; calls.push(`Content.getWork('${nextId}')`);
  } else {
    const d = Brain.nextFor({ exclude: [...seen] });
    if (!d.candidates.length) { seen.clear(); }
    decision = d; nextId = d.chosenId; calls.push(`Brain.nextFor() → 候选 ${d.candidates.length} 件`);
  }
  // 3) 前进 + 渲染
  fromId = cur; cur = nextId; seen.add(cur);
  renderWork(Content.getWork(cur));
  const doors = Brain.rankNeighbors(cur, fromId); lastDoors = doors;
  calls.push(`Content.neighbors('${cur}') → ${doors.length} 条`);
  renderDoors(doors);
  // 4) 面板
  renderInspector(calls, decision, entry);
  if (type !== 'start') flashFlow();
}

function renderInspector(calls, decision, entry) {
  // L1
  const s = Content.stats();
  $('#l1stats').textContent = `馆藏 ${s.total} 件 · 图谱 ${s.edges} 条边`;
  $('#l1calls').innerHTML = calls.map(c => `<div class="call">▸ ${esc(c)}</div>`).join('');
  // L2 信号流
  $('#l2log').innerHTML = Brain.log.map(e => {
    const ic = { heart: '♥', skip: '✕', door: '→', view: '👁', choose: '✓' }[e.type] || '•';
    const sign = e.weight > 0 ? `+${e.weight}` : `${e.weight}`;
    return `<div class="sig"><span class="si">${ic}</span><span class="st">${esc(e.title || '')}</span><span class="sw ${e.weight >= 0 ? 'p' : 'n'}">${sign}</span><span class="sm">${(e.themes || []).slice(0, 3).map(t => '#' + esc(t)).join(' ')}</span></div>`;
  }).join('') || '<div class="muted">(还没有信号 —— 点下面的 ♥ / ✕ / 门)</div>';
  // L3 画像:母题权重 + 长期质心摘要
  const p = Brain.profile;
  const top = Brain.topThemes(6); const max = Math.max(1, ...top.map(x => x[1]));
  const bars = top.length ? top.map(([t, v]) => `<div class="bar"><span class="bl">#${esc(t)}</span><span class="bt"><span class="bf" style="width:${Math.round(v / max * 100)}%"></span></span><span class="bv">${v}</span></div>`).join('') : '<div class="muted">画像还空,交互几下就会长出来</div>';
  const centroid = p.color || p.mood ? `<div class="call">质心:${p.color ? `色相${Math.round(p.color[0])}° 饱和${(p.color[1] * 100 | 0)}% 明度${(p.color[2] * 100 | 0)}%` : '—'} · ${p.mood ? `情绪 暖${p.mood.valence.toFixed(2)}/动${p.mood.arousal.toFixed(2)}` : '—'} · 心动集 ${p.loved.length} 件</div>` : '';
  $('#l3bars').innerHTML = bars + centroid;
  $('#l3explore').textContent = `探索胃口 exploreAppetite = ${p.exploreAppetite} · 累计正信号 n=${p.n}`;

  // ① 召回 / ② 打分 —— 来自 Brain.lastFunnel
  const f = Brain.lastFunnel;
  if (decision && decision.kind === 'door') {
    $('#l3recall').innerHTML = '<div class="muted">本步沿图谱前进(走"门",不经召回)</div>';
    $('#l3rank').innerHTML = '<div class="muted">门已按你的画像打分 → 见左侧"门"上的匹配分</div>';
  } else if (f) {
    $('#l3recall').innerHTML = `<div class="chips">${f.channels.map(c => `<span class="chip">${esc(c.label)} <b>×${c.n}</b></span>`).join('')}</div><div class="call" style="margin-top:4px">合并去重 → 候选池 <b>${f.poolN}</b> 件 → 打分排序如下</div>`;
    $('#l3rank').innerHTML = f.ranked.map((r, i) => `<div class="rk"><div class="rkhead"><span class="rkn">${i + 1}</span><span class="rt">${esc(r.title)}</span><span class="rs">${r.score}</span></div><div class="parts">${Object.entries(r.parts).map(([k, v]) => `<span class="pp">${esc(k)} <b>${v}</b></span>`).join('')}</div></div>`).join('');
  }
  // ③ 重排(决策)
  if (decision) {
    const cand = (f && decision.kind !== 'door') ? f.reranked : decision.candidates.map(c => ({ ...c }));
    const rows = cand.map((c, i) => {
      const win = c.chosen || c.id === decision.chosenId;
      const sc = (c.rerank != null && c.score != null) ? `重排 ${c.rerank} · 分 ${c.score}` : `${c.rerank != null ? c.rerank : c.score}`;
      return `<div class="cand ${win ? 'win' : ''}"><span class="cn">${win ? '✓' : i + 1}</span><span class="ct">${esc(c.title)}</span>${c.explore ? '<i>探索</i>' : ''}<span class="cs">${sc}</span></div>`;
    }).join('');
    $('#l3decision').innerHTML = `<div class="dlabel">决策(${decision.kind === 'door' ? '沿图谱' : '画来找你'}):${esc(decision.reason)}</div>${rows}`;
  }
}

// 权重旋钮:拖动即时改 Brain.weights / 探索胃口,并预览对当前候选的影响
const TUNE = [
  { grp: '美学奖励权重(v0.3)' },
  { k: 'aha', l: '顿悟 Aha', max: 2 }, { k: 'calm', l: '安静 Calm', max: 2 },
  { k: 'info', l: '信息 Info', max: 2 }, { k: 'growth', l: '成长 Growth', max: 2 },
  { grp: '重排 / 探索' },
  { k: 'diversity', l: '多样性', max: 1 }, { k: 'fatigue', l: '母题疲劳', max: 1.5 },
  { k: 'explore', l: '探索胃口', max: 0.8, appetite: true },
];
function buildTuner() {
  $('#tuner').innerHTML = TUNE.map(t => t.grp
    ? `<div class="tn grp">${t.grp}</div>`
    : `<div class="tn"><span class="tl">${t.l}</span><input type="range" min="0" max="${t.max}" step="0.05" value="${t.appetite ? Brain.profile.exploreAppetite : Brain.weights[t.k]}" data-k="${t.k}" data-ap="${t.appetite ? 1 : 0}"/><span class="tv" id="tv-${t.k}">${t.appetite ? Brain.profile.exploreAppetite : Brain.weights[t.k]}</span></div>`).join('');
  $('#tuner').querySelectorAll('input').forEach(inp => inp.oninput = () => {
    const v = +inp.value, k = inp.dataset.k;
    if (inp.dataset.ap === '1') Brain.profile.exploreAppetite = v; else Brain.weights[k] = v;
    $('#tv-' + k).textContent = v.toFixed(2);
    previewDecision();
  });
}
// 不前进,只用新权重重算"下一帧会推谁"并刷新面板(边调边看)
function previewDecision() {
  if (!cur) return;
  const d = Brain.nextFor({ exclude: [...seen] });
  renderInspector([`(预览)Brain.nextFor() → 候选 ${d.candidates.length} 件`], d, null);
  // 门也按新权重重排
  lastDoors = Brain.rankNeighbors(cur, fromId); renderDoors(lastDoors);
}

(async () => {
  await Content.load();
  $('#btnHeart').onclick = () => act('heart');
  $('#btnSkip').onclick = () => act('skip');
  $('#btnReset').onclick = () => { Brain.reset(); seen.clear(); fromId = null; cur = null; act('start'); };
  buildTuner();
  // 起点
  const d = Brain.nextFor({ exclude: [] }); cur = d.chosenId; seen.add(cur);
  renderWork(Content.getWork(cur));
  const doors = Brain.rankNeighbors(cur, null); lastDoors = doors; renderDoors(doors);
  renderInspector([`Brain.nextFor() → 起点`, `Content.neighbors('${cur}')`], d, null);
})();
