// 版本 B · 岔路 Crossroads —— lean-forward,沉浸 + 召唤门来掌舵
import { $, $$, el, esc, loadData, BY, bump, doorsFor, pickStart, artframe, matchedThemes, TYPE_LABEL } from './core.js';
import { initAmbient } from './ambient.js';

let amb = null;
let cur = null, fromSlug = null, visited = new Set(), loved = new Set(), tapT = null;
const canvas = $('#canvas'), pill = $('#pill'), panel = $('#panel'), sheet = $('#sheet'),
  burst = $('#burst'), vmeta = $('#vmeta');

function meta() { vmeta.textContent = `遇见 ${visited.size} · 心动 ${loved.size}`; }
function render() {
  const w = BY[cur]; visited.add(cur); meta();
  canvas.querySelectorAll('.artframe').forEach(n => n.remove());
  canvas.insertBefore(artframe(w, 'dissolve'), panel);
  if (amb) { amb.setMood(w); amb.breathe(true); }
  panel.classList.remove('open'); panel.innerHTML = `<div class="p-title">《${esc(w.title)}》</div>
    <div class="p-by">${esc(w.artist || '')} · ${esc(w.date || '')}</div>
    <div class="p-one">${esc(w.oneLiner)}</div>
    <div class="p-look">👁 <b>看这里</b> — ${esc(w.look)}</div>
    <div class="wi-themes" style="margin-top:12px">${(w.themes || []).map(t => `<span class="t">${esc(t)}</span>`).join('')}</div>`;
  const m = matchedThemes(w); pill.textContent = m.length ? '为你而来 · 因为你偏爱 ' + m.map(t => '#' + t).join(' ') : '轻点读它 · 推开一扇门继续'; pill.className = 'reason-pill';
  sheet.classList.remove('open');
}
function openSheet() {
  const doors = doorsFor(cur, fromSlug);
  const list = $('.sheet-doors', sheet); list.innerHTML = '';
  doors.forEach(d => {
    const b = el(`<button class="sdoor ${d.explore ? 'explore' : ''}">
      <span class="sd-chip">${d.explore ? '探索 ✦' : esc(TYPE_LABEL[d.type] || d.type)}</span>
      <div class="sd-why">${esc(d.why)}</div></button>`);
    b.onclick = () => { fromSlug = cur; cur = d.to; bump(BY[cur].themes, 1); render(); };
    list.appendChild(b);
  });
  sheet.classList.add('open');
}
function heart() {
  if (loved.has(cur)) loved.delete(cur);
  else { loved.add(cur); bump(BY[cur].themes, 2); burst.classList.remove('go'); void burst.offsetWidth; burst.classList.add('go'); }
  meta();
}
canvas.addEventListener('click', (e) => {
  if (e.target.closest('.panel')) return;
  if (tapT) { clearTimeout(tapT); tapT = null; heart(); }
  else tapT = setTimeout(() => { tapT = null; panel.classList.toggle('open'); }, 250);
});
$('#doorBtn').onclick = () => sheet.classList.contains('open') ? sheet.classList.remove('open') : openSheet();
sheet.addEventListener('click', e => { if (e.target === sheet) sheet.classList.remove('open'); });
document.addEventListener('keydown', e => {
  if (e.key === ' ' || e.key === 'ArrowUp') { e.preventDefault(); sheet.classList.contains('open') ? sheet.classList.remove('open') : openSheet(); }
  else if (e.key === 'i' || e.key === 'I') panel.classList.toggle('open');
  else if (e.key === 'h' || e.key === 'H') heart();
});

(async () => { await loadData(); amb = initAmbient(document.querySelector('.stage'), canvas); cur = pickStart(visited); render(); })();
