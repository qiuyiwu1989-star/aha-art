// 逛法 · 雾中之馆 —— 整片星图藏在雾里,你走到哪、点亮到哪
import { $, el, esc, loadData, WORKS, BY, ADJ, GRAPH, pickStart, artframe, thumbImg } from './core.js';

const SPACE = 1800;
const galaxy = $('#galaxy'), space = $('#gspace'), detail = $('#gdetail'), prog = $('#fogProgress');
let scale = 1, tx = 0, ty = 0, dragging = false, moved = false, last = null;
let P = {}, lit = new Set(), nodeEls = {}, svg = null;

function apply() { space.style.transform = `translate(${tx}px,${ty}px) scale(${scale})`; }
function near() { const n = new Set(); lit.forEach(s => ADJ[s].forEach(e => { if (!lit.has(e.to)) n.add(e.to); })); return n; }
function refresh() {
  const nr = near();
  WORKS.forEach(w => {
    const st = lit.has(w.slug) ? 'lit' : nr.has(w.slug) ? 'near' : 'fog';
    nodeEls[w.slug].className = 'gnode ' + st;
  });
  // 边:两端都点亮=实线;一端点亮=虚线;否则隐藏
  svg.querySelectorAll('line').forEach(ln => {
    const a = ln.dataset.a, b = ln.dataset.b;
    const both = lit.has(a) && lit.has(b), one = lit.has(a) || lit.has(b);
    ln.style.display = (both || one) ? '' : 'none';
    ln.classList.toggle('dim', !both);
  });
  prog.textContent = `已点亮 ${lit.size} / ${WORKS.length} · ${WORKS.length - lit.size ? '其余仍在雾中' : '整片星图被你点亮了 ✦'}`;
}
function light(slug) { lit.add(slug); refresh(); }
function openDetail(w) {
  detail.querySelector('.gd-holder').innerHTML = ''; detail.querySelector('.gd-holder').appendChild(artframe(w));
  detail.querySelector('.gd-title').textContent = `《${w.title}》`;
  detail.querySelector('.gd-by').textContent = `${w.artist || ''} · ${w.date || ''}`;
  detail.querySelector('.gd-one').textContent = w.oneLiner || '';
  detail.classList.add('open');
}
(async () => {
  await loadData();
  const cx = SPACE / 2, cy = SPACE / 2, K = (SPACE / 2) / Math.sqrt(WORKS.length) * 0.92;
  WORKS.forEach((w, i) => { const a = i * 2.399963, r = i === 0 ? 0 : K * Math.sqrt(i + .5); P[w.slug] = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }; });
  const seen = new Set(); let lines = '';
  GRAPH.edges.forEach(e => { const k = [e.a, e.b].sort().join('|'); if (seen.has(k)) return; seen.add(k); const a = P[e.a], b = P[e.b]; lines += `<line data-a="${e.a}" data-b="${e.b}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`; });
  svg = el(`<svg width="${SPACE}" height="${SPACE}">${lines}</svg>`); space.appendChild(svg);
  WORKS.forEach(w => {
    const n = el(`<div class="gnode fog" style="left:${P[w.slug].x}px;top:${P[w.slug].y}px"><span class="glab">${esc(w.artist || w.title)}</span></div>`);
    n.insertBefore(thumbImg(w), n.firstChild);
    n.addEventListener('click', () => { if (moved) return; if (lit.has(w.slug)) openDetail(w); else if (near().has(w.slug)) light(w.slug); });
    nodeEls[w.slug] = n; space.appendChild(n);
  });
  lit.add(pickStart()); refresh();
  const vw = innerWidth, vh = innerHeight; scale = Math.min(vw, vh) / SPACE * 0.82;
  tx = (vw - SPACE * scale) / 2; ty = (vh - SPACE * scale) / 2; apply();
  galaxy.addEventListener('pointerdown', e => { dragging = true; moved = false; last = [e.clientX, e.clientY]; galaxy.classList.add('grabbing'); });
  addEventListener('pointermove', e => { if (!dragging) return; const dx = e.clientX - last[0], dy = e.clientY - last[1]; if (Math.abs(dx) + Math.abs(dy) > 4) moved = true; tx += dx; ty += dy; last = [e.clientX, e.clientY]; apply(); });
  addEventListener('pointerup', () => { dragging = false; galaxy.classList.remove('grabbing'); });
  galaxy.addEventListener('wheel', e => { e.preventDefault(); const f = e.deltaY < 0 ? 1.12 : .89, ns = Math.max(.35, Math.min(3.2, scale * f)); tx = e.clientX - (e.clientX - tx) * (ns / scale); ty = e.clientY - (e.clientY - ty) * (ns / scale); scale = ns; apply(); }, { passive: false });
  detail.querySelector('.gd-x').onclick = () => detail.classList.remove('open');
  detail.addEventListener('click', e => { if (e.target === detail) detail.classList.remove('open'); });
})();
