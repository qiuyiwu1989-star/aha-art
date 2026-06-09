// 概念 3 · 两画之间 —— 图谱里的最短路径(六度名画)
import { $, el, esc, loadData, WORKS, BY, ADJ, TYPE_LABEL, artframe } from './core.js';

const selA = $('#selA'), selB = $('#selB'), head = $('#phead'), line = $('#pathline');

function bfs(a, b) {
  if (a === b) return [{ slug: a }];
  const prev = { [a]: null }, edge = {}, q = [a];
  while (q.length) {
    const cur = q.shift();
    for (const e of ADJ[cur]) {
      if (e.to in prev) continue;
      prev[e.to] = cur; edge[e.to] = e;
      if (e.to === b) {
        const path = []; let n = b;
        while (n !== null) { path.unshift({ slug: n, via: edge[n] }); n = prev[n]; }
        return path;
      }
      q.push(e.to);
    }
  }
  return null;
}
function show() {
  const a = selA.value, b = selB.value;
  const path = bfs(a, b);
  line.innerHTML = '';
  if (!path) { head.textContent = '这两幅之间还没连通(demo 数据有限)。'; return; }
  const hops = path.length - 1;
  head.innerHTML = hops === 0 ? '同一幅画。' :
    `从《${esc(BY[a].title)}》到《${esc(BY[b].title)}》,只隔 <b style="color:var(--accent)">${hops}</b> 步。`;
  path.forEach((p, i) => {
    if (p.via) {
      line.appendChild(el(`<div class="plink"><div class="pl-arr">→</div>
        <div class="pl-chip">${esc(TYPE_LABEL[p.via.type] || p.via.type)}</div>
        <div class="pl-why">${esc(p.via.why)}</div></div>`));
    }
    const w = BY[p.slug];
    const step = el(`<div class="pstep"><div class="mini"></div></div>`);
    const mini = $('.mini', step); mini.appendChild(artframe(w));
    mini.appendChild(el(`<div class="cap">《${esc(w.title)}》<br/>${esc(w.artist || '')}</div>`));
    line.appendChild(step);
  });
}
(async () => {
  await loadData();
  const opts = WORKS.slice().sort((a, b) => (a.year || 0) - (b.year || 0))
    .map(w => `<option value="${w.slug}">${esc(w.title)} · ${esc(w.artist || '')}</option>`).join('');
  selA.innerHTML = opts; selB.innerHTML = opts;
  selA.value = 'great-wave'; selB.value = 'paris-rainy';
  $('#goPath').onclick = show;
  selA.onchange = show; selB.onchange = show;
  show();
})();
