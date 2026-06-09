// 逛法 · 银河漫游 —— 全库可平移缩放的星图
import { $, el, esc, loadData, WORKS, GRAPH, artframe, thumbImg } from './core.js';

const SPACE = 1800;
const galaxy = $('#galaxy'), space = $('#gspace'), detail = $('#gdetail');
let scale = 1, tx = 0, ty = 0, dragging = false, moved = false, last = null;

function apply() { space.style.transform = `translate(${tx}px,${ty}px) scale(${scale})`; }
function pos() {
  const cx = SPACE / 2, cy = SPACE / 2, C = (SPACE / 2) / Math.sqrt(WORKS.length) * 0.92, p = {};
  WORKS.forEach((w, i) => { const a = i * 2.399963, r = i === 0 ? 0 : C * Math.sqrt(i + .5); p[w.slug] = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }; });
  return p;
}
function openDetail(w) {
  detail.querySelector('.gd-holder').innerHTML = '';
  detail.querySelector('.gd-holder').appendChild(artframe(w));
  detail.querySelector('.gd-title').textContent = `《${w.title}》`;
  detail.querySelector('.gd-by').textContent = `${w.artist || ''} · ${w.date || ''}`;
  detail.querySelector('.gd-one').textContent = w.oneLiner || '';
  detail.classList.add('open');
}
(async () => {
  await loadData();
  const p = pos();
  // 边
  const seen = new Set(); let lines = '';
  GRAPH.edges.forEach(e => { const k = [e.a, e.b].sort().join('|'); if (seen.has(k)) return; seen.add(k); const a = p[e.a], b = p[e.b]; lines += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`; });
  space.appendChild(el(`<svg width="${SPACE}" height="${SPACE}">${lines}</svg>`));
  // 节点
  WORKS.forEach(w => {
    const n = el(`<div class="gnode" style="left:${p[w.slug].x}px;top:${p[w.slug].y}px"><span class="glab">${esc(w.artist || w.title)}</span></div>`);
    n.insertBefore(thumbImg(w), n.firstChild);
    n.addEventListener('click', () => { if (!moved) openDetail(w); });
    space.appendChild(n);
  });
  // 初始适配:居中铺满
  const vw = innerWidth, vh = innerHeight;
  scale = Math.min(vw, vh) / SPACE * 0.82;
  tx = (vw - SPACE * scale) / 2; ty = (vh - SPACE * scale) / 2; apply();
  // 拖拽平移
  galaxy.addEventListener('pointerdown', e => { dragging = true; moved = false; last = [e.clientX, e.clientY]; galaxy.classList.add('grabbing'); });
  addEventListener('pointermove', e => { if (!dragging) return; const dx = e.clientX - last[0], dy = e.clientY - last[1]; if (Math.abs(dx) + Math.abs(dy) > 4) moved = true; tx += dx; ty += dy; last = [e.clientX, e.clientY]; apply(); });
  addEventListener('pointerup', () => { dragging = false; galaxy.classList.remove('grabbing'); });
  // 滚轮缩放(以光标为锚)
  galaxy.addEventListener('wheel', e => {
    e.preventDefault();
    const f = e.deltaY < 0 ? 1.12 : 0.89, ns = Math.max(.35, Math.min(3.2, scale * f));
    tx = e.clientX - (e.clientX - tx) * (ns / scale); ty = e.clientY - (e.clientY - ty) * (ns / scale); scale = ns; apply();
  }, { passive: false });
  detail.querySelector('.gd-x').onclick = () => detail.classList.remove('open');
  detail.addEventListener('click', e => { if (e.target === detail) detail.classList.remove('open'); });
})();
