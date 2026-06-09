// 版本 A · 漂流 Drift —— lean-back,零决策,被带着走
import { $, el, esc, loadData, BY, bump, bestNext, pickStart, artframe, matchedThemes, TYPE_LABEL } from './core.js';
import { initAmbient } from './ambient.js';

let amb = null;
let cur = null, fromSlug = null, visited = new Set(), loved = new Set();
let auto = null, tapT = null;

const canvas = $('#canvas'), whisper = $('#whisper'), pill = $('#pill'),
  lf = $('#linkflash'), panel = $('#panel'), burst = $('#burst'), vmeta = $('#vmeta');

function meta() { vmeta.textContent = `遇见 ${visited.size} · 心动 ${loved.size}`; }
function arrivalPill(link) {
  if (!link) { pill.textContent = '为你而来 · 今天最贴你的一帧'; pill.className = 'reason-pill'; return; }
  if (link.explore) { pill.textContent = '踮脚一张 · 舒适区之外'; pill.className = 'reason-pill explore'; return; }
  const m = matchedThemes(BY[cur]); pill.textContent = m.length ? '为你而来 · 因为你偏爱 ' + m.map(t => '#' + t).join(' ') : '顺着上一幅,走到这里'; pill.className = 'reason-pill';
}
function render(arrivalLink) {
  const w = BY[cur]; visited.add(cur); meta();
  canvas.querySelectorAll('.artframe').forEach(n => n.remove());
  const af = artframe(w, 'dissolve'); canvas.insertBefore(af, whisper);
  if (amb) { amb.setMood(w); amb.breathe(true); }
  // 一句点破:自动浮现 3.5s 后淡去
  whisper.innerHTML = `${esc(w.oneLiner)}`;
  whisper.classList.add('show'); clearTimeout(whisper._t);
  whisper._t = setTimeout(() => whisper.classList.remove('show'), 3600);
  // 信息面板内容
  panel.innerHTML = `<div class="p-title">《${esc(w.title)}》</div>
    <div class="p-by">${esc(w.artist || '')} · ${esc(w.date || '')}</div>
    <div class="p-one">${esc(w.oneLiner)}</div>
    <div class="p-look">👁 <b>看这里</b> — ${esc(w.look)}</div>`;
  arrivalPill(arrivalLink);
}
function flashLink(link, cb) {
  lf.querySelector('.lf-chip').textContent = link.explore ? '探索 ✦' : (TYPE_LABEL[link.type] || link.type);
  lf.querySelector('.lf-why').textContent = link.why;
  lf.classList.add('show');
  setTimeout(() => { lf.classList.remove('show'); cb(); }, 900);
}
function advance() {
  const nx = bestNext(cur, fromSlug); if (!nx) return;
  flashLink(nx, () => { fromSlug = cur; cur = nx.to; bump(BY[cur].themes, 1); render(nx); });
}
function heart() {
  if (loved.has(cur)) loved.delete(cur);
  else { loved.add(cur); bump(BY[cur].themes, 2); burst.classList.remove('go'); void burst.offsetWidth; burst.classList.add('go'); }
  meta();
}
// 单击=漂流,双击=心动
canvas.addEventListener('click', (e) => {
  if (e.target.closest('.panel')) return;
  if (tapT) { clearTimeout(tapT); tapT = null; heart(); }
  else tapT = setTimeout(() => { tapT = null; advance(); }, 250);
});
$('#infoBtn').onclick = () => panel.classList.toggle('open');
$('#autoBtn').onclick = (e) => {
  if (auto) { clearInterval(auto); auto = null; e.target.textContent = '▷ 环境模式'; e.target.classList.remove('primary'); }
  else { auto = setInterval(advance, 16000); e.target.textContent = '⏸ 环境模式'; e.target.classList.add('primary'); }
};
document.addEventListener('keydown', e => {
  if (e.key === ' ' || e.key === 'ArrowRight') { e.preventDefault(); advance(); }
  else if (e.key === 'i' || e.key === 'I') panel.classList.toggle('open');
  else if (e.key === 'h' || e.key === 'H') heart();
});

(async () => { await loadData(); amb = initAmbient(document.querySelector('.stage'), canvas); cur = pickStart(visited); render(null); })();
