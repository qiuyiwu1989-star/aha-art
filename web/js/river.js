// 概念 1 · 母题之河 —— 一个母题穿越古今中外
import { $, $$, el, esc, loadData, WORKS, artframe } from './core.js';

const chips = $('#chips'), river = $('#river'), meta = $('#rmeta'), lb = $('#lightbox');

function themeFreq() {
  const m = {};
  WORKS.forEach(w => (w.themes || []).forEach(t => m[t] = (m[t] || 0) + 1));
  return Object.entries(m).filter(([, n]) => n >= 2).sort((a, b) => b[1] - a[1]);
}
function openLB(w) {
  lb.querySelector('.lb-holder').innerHTML = '';
  lb.querySelector('.lb-holder').appendChild(artframe(w));
  lb.querySelector('.lb-title').textContent = `《${w.title}》`;
  lb.querySelector('.lb-by').textContent = `${w.artist || ''} · ${w.date || ''}`;
  lb.querySelector('.lb-one').textContent = w.oneLiner || '';
  lb.classList.add('open');
}
function showTheme(theme) {
  $$('.chip', chips).forEach(c => c.classList.toggle('on', c.dataset.t === theme));
  const list = WORKS.filter(w => (w.themes || []).includes(theme))
    .sort((a, b) => (a.year || 0) - (b.year || 0));
  const span = list.length ? (list[list.length - 1].year - list[0].year) : 0;
  meta.textContent = `「${theme}」· ${list.length} 幅 · 跨越约 ${Math.max(span, 0)} 年 —— 顺流而下,看同一种东西如何在不同时代、不同文明里被反复打动。`;
  river.innerHTML = '';
  list.forEach(w => {
    const stop = el(`<div class="river-stop">
      <div class="mini"></div>
      <div class="ryr">${esc(String(w.year || w.date || ''))}</div>
      <div class="rart">${esc(w.artist || '')}</div></div>`);
    const mini = $('.mini', stop); mini.appendChild(artframe(w));
    mini.appendChild(el(`<div class="cap">《${esc(w.title)}》</div>`));
    mini.onclick = () => openLB(w);
    river.appendChild(stop);
  });
}
(async () => {
  await loadData();
  themeFreq().forEach(([t, n], i) => {
    const c = el(`<button class="chip" data-t="${esc(t)}">${esc(t)}<span class="ct">${n}</span></button>`);
    c.onclick = () => showTheme(t); chips.appendChild(c);
  });
  lb.querySelector('.lb-x').onclick = () => lb.classList.remove('open');
  lb.onclick = e => { if (e.target === lb) lb.classList.remove('open'); };
  // 默认选频次最高的母题
  const first = themeFreq()[0]; if (first) showTheme(first[0]);
})();
