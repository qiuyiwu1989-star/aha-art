// ═══ aha · 共享内核(被各交互版本复用)═══
export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];
export const el = (h) => { const t = document.createElement('template'); t.innerHTML = h.trim(); return t.content.firstChild; };
export const esc = (s) => String(s || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export let WORKS = [], BY = {}, ADJ = {}, GRAPH = null, TYPE_LABEL = {};
const LS = 'aha.taste.v1';
let taste = JSON.parse(localStorage.getItem(LS) || '{}');

export async function loadData() {
  [WORKS, GRAPH] = await Promise.all([
    fetch('data/artworks.json').then(r => r.json()),
    fetch('data/graph.json').then(r => r.json()),
  ]);
  WORKS.forEach(w => { BY[w.slug] = w; ADJ[w.slug] = []; });
  GRAPH.edges.forEach(e => {
    ADJ[e.a].push({ to: e.b, type: e.type, why: e.why });
    ADJ[e.b].push({ to: e.a, type: e.type, why: e.why });
  });
  TYPE_LABEL = GRAPH.typeLabels;
  // 无口味记录时给个轻底,避免冷启动空转(对比页里不强制 onboarding)
  if (!Object.keys(taste).length) WORKS.forEach(w => bump(w.themes, 0.1));
  return { WORKS, BY, ADJ, GRAPH, TYPE_LABEL };
}

export function bump(themes, w) { (themes || []).forEach(t => taste[t] = (taste[t] || 0) + w); localStorage.setItem(LS, JSON.stringify(taste)); }
export function score(work) { return (work.themes || []).reduce((s, t) => s + (taste[t] || 0), 0); }
export function topThemes(n = 4) { return Object.entries(taste).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, n).map(x => x[0]); }
export function matchedThemes(work, k = 2) { const top = topThemes(6); return (work.themes || []).filter(t => top.includes(t)).slice(0, k); }

// 排好序的邻居(去重、排除来路、按口味降序)
export function rankedNeighbors(slug, fromSlug = null) {
  let nb = ADJ[slug].filter(d => d.to !== fromSlug); if (!nb.length) nb = ADJ[slug].slice();
  const bt = {}; nb.forEach(d => { if (!bt[d.to]) bt[d.to] = d; });
  return Object.values(bt).map(d => ({ ...d, s: score(BY[d.to]) })).sort((a, b) => b.s - a.s);
}
// 三扇门:最贴口味 2 + 反茧房探索 1
export function doorsFor(slug, fromSlug = null) {
  const list = rankedNeighbors(slug, fromSlug);
  if (list.length <= 3) return list.map(d => ({ ...d, explore: false }));
  return [...list.slice(0, 2).map(d => ({ ...d, explore: false })), { ...list[list.length - 1], explore: true }];
}
export function bestNext(slug, fromSlug = null) {
  const list = rankedNeighbors(slug, fromSlug);
  // 90% 走最贴口味,10% 踮脚(反茧房),让漂流也偶有意外
  if (list.length > 3 && Math.random() < 0.18) return { ...list[list.length - 1], explore: true };
  return list[0] ? { ...list[0], explore: false } : null;
}
export function pickStart(visited = new Set()) {
  const unseen = WORKS.filter(w => !visited.has(w.slug));
  return (unseen.length ? unseen : WORKS).slice().sort((a, b) => score(b) - score(a))[0].slug;
}

// 真实小尺寸压缩图(IIIF 200px);用于色块/星点/散点等小图视图
export function thumb(w) { return w.thumb || (w.image || '').replace(/\/\d+,\//, '/200,/') || w.lqip || ''; }
// 生成一个会优雅降级的小图 <img>(真图失败 → lqip 占位)
export function thumbImg(w, cls = '') {
  const i = document.createElement('img'); if (cls) i.className = cls; i.loading = 'lazy'; i.alt = '';
  i.onerror = () => { i.onerror = null; if (w.lqip) i.src = w.lqip; };
  i.src = thumb(w); return i;
}

// 可加载图(blur-up + 降尺寸重试 + 文字兜底)
export function artframe(work, cls = '') {
  const f = el(`<div class="artframe ${cls}">
    <img class="blur" src="${work.lqip || ''}" alt="" aria-hidden="true"/>
    <img class="full" alt="${esc(work.alt || work.title)}"/>
    <div class="fallback"><div class="ft">《${esc(work.title)}》</div>
      <div class="fa">${esc(work.artist || '')}</div><div class="fn">${esc(work.date || '')}</div></div></div>`);
  const full = $('.full', f); let retried = false;
  full.onload = () => full.classList.add('loaded');
  full.onerror = () => { if (!retried && /\/\d+,\//.test(work.image)) { retried = true; full.src = work.image.replace(/\/\d+,\//, '/600,/'); } else f.classList.add('failed'); };
  full.src = work.image;
  return f;
}
