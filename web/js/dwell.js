// 逛法 · 专注单幅 —— 停在一幅画,逐层揭开(集中、沉浸、深)
import { $, el, esc, loadData, BY, bump, bestNext, pickStart, rankedNeighbors, artframe, TYPE_LABEL } from './core.js';
import { initAmbient } from './ambient.js';

let amb = null, cur = null, fromSlug = null, step = 0, visited = new Set();
const canvas = $('#canvas'), layer = $('#layer'), dots = $('#dots'), nextBtn = $('#nextBtn'), meta = $('#vmeta');
const STEPS = 4; // 0 静默 / 1 点破 / 2 看这里(细节) / 3 顺它走

function setFull(transform, origin) {
  const f = canvas.querySelector('.full'); if (!f) return;
  f.classList.add('kenburns'); if (origin) f.style.transformOrigin = origin; f.style.transform = transform;
}
function renderWork() {
  const w = BY[cur]; visited.add(cur); meta.textContent = `专注 · 已遇见 ${visited.size}`;
  canvas.querySelectorAll('.artframe').forEach(n => n.remove());
  canvas.insertBefore(artframe(w, 'dissolve'), layer);
  if (amb) { amb.setMood(w); amb.breathe(true); }
  step = 0; renderStep();
}
function renderStep() {
  $$dots(); nextBtn.textContent = step >= STEPS - 1 ? '换一幅 →' : '深入一层 →';
  const w = BY[cur];
  layer.classList.remove('show');
  setTimeout(() => {
    if (step === 0) { layer.innerHTML = ''; setFull('scale(1)'); }
    else if (step === 1) { layer.innerHTML = `<div class="dwell-one">${esc(w.oneLiner)}</div>`; setFull('scale(1)'); }
    else if (step === 2) { layer.innerHTML = `<div class="dwell-look">👁 <b>看这里</b> — ${esc(w.look)}</div>`; setFull('scale(1.6)', '38% 32%'); }
    else {
      setFull('scale(1)');
      const nbs = rankedNeighbors(cur, fromSlug).slice(0, 3);
      layer.innerHTML = `<div class="dwell-doors"></div>`;
      const dd = layer.querySelector('.dwell-doors');
      nbs.forEach(n => {
        const b = el(`<button class="dd"><span class="ddc">顺它走 · ${esc(TYPE_LABEL[n.type] || n.type)}</span>${esc(n.why)}</button>`);
        b.onclick = () => { fromSlug = cur; cur = n.to; bump(BY[cur].themes, 1); renderWork(); };
        dd.appendChild(b);
      });
    }
    if (step > 0) layer.classList.add('show');
  }, 180);
}
function $$dots() { dots.innerHTML = ''; for (let i = 0; i < STEPS; i++) dots.appendChild(el(`<div class="ds ${i <= step ? 'on' : ''}"></div>`)); }
function next() { if (step >= STEPS - 1) { const nx = bestNext(cur, fromSlug); if (nx) { fromSlug = cur; cur = nx.to; bump(BY[cur].themes, 1); } renderWork(); } else { step++; renderStep(); } }

(async () => {
  await loadData();
  amb = initAmbient(document.querySelector('.stage'), canvas);
  cur = pickStart(visited); renderWork();
  nextBtn.onclick = next;
  canvas.addEventListener('click', e => { if (!e.target.closest('.dwell-doors')) next(); });
  document.addEventListener('keydown', e => { if (e.key === ' ' || e.key === 'ArrowRight') { e.preventDefault(); next(); } });
})();
