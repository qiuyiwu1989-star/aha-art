// 版本 C · 并置 Resonance —— 连接优先,每屏都是一对「啊,这两个」
import { $, $$, el, esc, loadData, BY, bump, rankedNeighbors, pickStart, artframe, TYPE_LABEL } from './core.js';
import { initAmbient } from './ambient.js';

let amb = null;
let cur = null, fromSlug = null, partnerIdx = 0, visited = new Set(), loved = new Set(), tapT = null;
const dip = $('#diptych'), panel = $('#panel'), burst = $('#burst'), vmeta = $('#vmeta');

function meta() { vmeta.textContent = `遇见 ${visited.size} · 心动 ${loved.size}`; }
function render() {
  const w = BY[cur]; visited.add(cur); meta();
  const nbs = rankedNeighbors(cur, fromSlug);
  const link = nbs.length ? nbs[((partnerIdx % nbs.length) + nbs.length) % nbs.length] : null;
  dip.innerHTML = '';
  const big = el(`<div class="dwork big dissolve"><div class="dw-cap">${esc(w.artist || '')} · ${esc(w.date || '')}</div></div>`);
  big.insertBefore(artframe(w), big.firstChild);
  dip.appendChild(big);
  if (link) {
    const p = BY[link.to];
    const mid = el(`<div class="dlink dissolve"><div class="dl-chip">${esc(TYPE_LABEL[link.type] || link.type)}</div>
      <div class="dl-why">${esc(link.why)}</div><div class="dl-arrow">↓</div>
      <div style="font-family:var(--mono);font-size:10px;color:#9a917f">点右图,走进它 · ↻ 换一个共鸣</div></div>`);
    dip.appendChild(mid);
    const small = el(`<div class="dwork small dissolve"><div class="dw-cap">${esc(p.artist || '')}</div></div>`);
    small.insertBefore(artframe(p), small.firstChild);
    small.onclick = () => { fromSlug = cur; cur = link.to; partnerIdx = 0; bump(BY[cur].themes, 1); render(); };
    dip.appendChild(small);
  }
  panel.innerHTML = `<div class="p-title">《${esc(w.title)}》</div>
    <div class="p-by">${esc(w.artist || '')} · ${esc(w.date || '')}</div>
    <div class="p-one">${esc(w.oneLiner)}</div>
    <div class="p-look">👁 <b>看这里</b> — ${esc(w.look)}</div>`;
  panel.classList.remove('open');
  if (amb) amb.setMood(w);
}
function heart() {
  if (loved.has(cur)) loved.delete(cur);
  else { loved.add(cur); bump(BY[cur].themes, 2); burst.classList.remove('go'); void burst.offsetWidth; burst.classList.add('go'); }
  meta();
}
// 点大图:单击读它,双击心动
$('#diptych').addEventListener('click', (e) => {
  const big = e.target.closest('.dwork.big'); if (!big) return;
  if (tapT) { clearTimeout(tapT); tapT = null; heart(); }
  else tapT = setTimeout(() => { tapT = null; panel.classList.toggle('open'); }, 250);
});
$('#cycleBtn').onclick = () => { partnerIdx++; render(); };
$('#infoBtn').onclick = () => panel.classList.toggle('open');
document.addEventListener('keydown', e => {
  if (e.key === ' ' || e.key === 'ArrowRight') { e.preventDefault(); partnerIdx++; render(); }
  else if (e.key === 'i' || e.key === 'I') panel.classList.toggle('open');
  else if (e.key === 'h' || e.key === 'H') heart();
});

(async () => { await loadData(); amb = initAmbient(document.querySelector('.stage'), $('#diptych')); cur = pickStart(visited); render(); })();
