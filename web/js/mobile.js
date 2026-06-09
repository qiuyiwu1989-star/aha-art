// 手机原生版 —— 一根拇指走完:上滑下一幅 / 左右滑岔路 / 下滑读它 / 双击心动 / 长按凑近 / 捏合放大 / 摇一摇惊喜
import { $, el, esc, loadData, BY, bump, bestNext, rankedNeighbors, pickStart, matchedThemes, artframe, TYPE_LABEL, WORKS } from './core.js';
import { initAmbient } from './ambient.js';

let amb = null, cur = null, fromSlug = null, visited = new Set(), loved = new Set();
let doorL = null, doorR = null;
const stage = $('#stage'), canvas = $('#canvas'), pill = $('#pill'), info = $('#info'),
  burst = $('#burst'), edgeL = $('#edgeL'), edgeR = $('#edgeR'), hint = $('#mhint'), meta = $('#vmeta');

function vibrate(ms) { try { navigator.vibrate && navigator.vibrate(ms); } catch { } }
function reasonText(reason) {
  if (reason === 'random') return '不期而遇 · 摇出来的一帧';
  if (reason === 'explore') return '踮脚一张 · 舒适区之外';
  const m = matchedThemes(BY[cur]); return m.length ? '为你而来 · 因为你偏爱 ' + m.map(t => '#' + t).join(' ') : '顺着上一幅,走到这里';
}
function render(reason) {
  const w = BY[cur]; visited.add(cur); meta.textContent = `${visited.size} 幅 · ♥ ${loved.size}`;
  canvas.querySelectorAll('.artframe').forEach(n => n.remove());
  canvas.insertBefore(artframe(w, 'dissolve'), info);
  if (amb) amb.setMood(w);
  pill.textContent = reasonText(reason); pill.className = 'reason-pill' + (reason === 'explore' ? ' explore' : '');
  // 两条岔路
  const doors = rankedNeighbors(cur, fromSlug);
  doorL = doors[0] || null;
  doorR = (doors.length > 1 ? (doors[doors.length - 1].to !== (doorL && doorL.to) ? doors[doors.length - 1] : doors[1]) : null);
  setEdge(edgeL, doorL, '←'); setEdge(edgeR, doorR, '→');
  // 信息
  info.className = 'panel'; info.innerHTML = `<div class="p-title">《${esc(w.title)}》</div>
    <div class="p-by">${esc(w.artist || '')} · ${esc(w.date || '')}</div>
    <div class="p-one">${esc(w.oneLiner)}</div>
    <div class="p-look">👁 <b>看这里</b> — ${esc(w.look)}</div>`;
}
function setEdge(node, door, arrow) {
  if (!door) { node.classList.remove('show'); return; }
  node.innerHTML = `<span class="eh-chip">${arrow} ${esc(TYPE_LABEL[door.type] || door.type)}</span>${esc(BY[door.to].title)}`;
  node.classList.add('show');
}
function go(slug, reason) { fromSlug = cur; cur = slug; bump(BY[slug].themes, 1); render(reason); }
function next() { const n = bestNext(cur, fromSlug); if (n) go(n.to, n.explore ? 'explore' : 'taste'); }
function dice() { const un = WORKS.filter(w => !visited.has(w.slug)); const pool = un.length ? un : WORKS.filter(w => w.slug !== cur); const p = pool[Math.floor(Math.random() * pool.length)]; fromSlug = null; cur = p.slug; bump(p.themes, .5); render('random'); vibrate(8); }
function heart() {
  const w = BY[cur];
  if (loved.has(cur)) loved.delete(cur);
  else { loved.add(cur); bump(w.themes, 2); burst.classList.remove('go'); void burst.offsetWidth; burst.classList.add('go'); vibrate(14); }
  meta.textContent = `${visited.size} 幅 · ♥ ${loved.size}`;
}
function toggleInfo() { info.classList.toggle('open'); }
function full() { return canvas.querySelector('.full'); }
function zoomDetail(on) { const f = full(); if (!f) return; f.classList.add('mzoom'); f.style.transformOrigin = '50% 38%'; f.style.transform = on ? 'scale(1.7)' : 'scale(1)'; }

// ── 手势 ──
let sx = 0, sy = 0, st = 0, moved = false, longT = null, longFired = false, lastTap = 0, pinchStart = 0, pinching = false;
canvas.addEventListener('touchstart', e => {
  if (e.touches.length === 2) { pinching = true; pinchStart = dist2(e.touches); return; }
  const t = e.touches[0]; sx = t.clientX; sy = t.clientY; st = Date.now(); moved = false; longFired = false;
  longT = setTimeout(() => { if (!moved) { longFired = true; zoomDetail(true); } }, 480);
}, { passive: true });
canvas.addEventListener('touchmove', e => {
  if (pinching && e.touches.length === 2) { const f = full(); if (f) { const s = Math.max(1, Math.min(3, dist2(e.touches) / pinchStart)); f.classList.remove('mzoom'); f.style.transformOrigin = '50% 45%'; f.style.transform = `scale(${s})`; } return; }
  const t = e.touches[0]; if (Math.abs(t.clientX - sx) + Math.abs(t.clientY - sy) > 12) { moved = true; clearTimeout(longT); }
}, { passive: true });
canvas.addEventListener('touchend', e => {
  clearTimeout(longT);
  if (pinching) { pinching = false; zoomDetail(false); return; }
  if (longFired) { zoomDetail(false); return; }
  const t = (e.changedTouches && e.changedTouches[0]) || {}; const dx = (t.clientX || sx) - sx, dy = (t.clientY || sy) - sy, dt = Date.now() - st;
  const ax = Math.abs(dx), ay = Math.abs(dy);
  if (ax < 14 && ay < 14 && dt < 280) { // 轻点 → 双击判定
    const now = Date.now(); if (now - lastTap < 300) { heart(); lastTap = 0; } else lastTap = now;
    fadeHint(); return;
  }
  fadeHint();
  if (ay > ax && ay > 45) { if (dy < 0) next(); else toggleInfo(); }          // 上滑下一幅 / 下滑读它
  else if (ax > ay && ax > 45) { const d = dx < 0 ? doorL : doorR; if (d) go(d.to, d === doorR && d.explore ? 'explore' : 'taste'); }  // 左/右滑岔路
}, { passive: true });
function dist2(ts) { const a = ts[0], b = ts[1]; return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY); }
function fadeHint() { hint && hint.classList.add('fade'); }

// 桌面可测:箭头键 + 双击
document.addEventListener('keydown', e => {
  if (e.key === 'ArrowUp') next(); else if (e.key === 'ArrowDown') toggleInfo();
  else if (e.key === 'ArrowLeft' && doorL) go(doorL.to, 'taste'); else if (e.key === 'ArrowRight' && doorR) go(doorR.to, doorR.explore ? 'explore' : 'taste');
  else if (e.key === 'h') heart(); else if (e.key === 'r') dice();
});
canvas.addEventListener('dblclick', heart);

// 摇一摇 → 不期而遇(需要时申请权限)
function attachShake() {
  let last = 0, lx = 0, ly = 0, lz = 0;
  addEventListener('devicemotion', ev => {
    const a = ev.accelerationIncludingGravity; if (!a) return;
    const now = Date.now(); if (now - last < 800) return;
    const d = Math.abs(a.x - lx) + Math.abs(a.y - ly) + Math.abs(a.z - lz);
    lx = a.x; ly = a.y; lz = a.z;
    if (d > 38) { last = now; dice(); }
  });
}

// 图例:最先挂关闭——按钮 / 整层任意点触都能关,且 JS 兜底隐藏(不依赖 CSS,也不受后续报错影响)
const legend = $('#legend');
function closeLegend() { if (!legend) return; legend.classList.add('hide'); legend.style.pointerEvents = 'none'; legend.style.opacity = '0'; setTimeout(() => { legend.style.display = 'none'; }, 450); }
if ($('#legendGo')) $('#legendGo').onclick = closeLegend;
if (legend) { legend.addEventListener('click', closeLegend); legend.addEventListener('touchend', closeLegend, { passive: true }); }

(async () => {
  try {
    await loadData();
    amb = initAmbient(stage, null);      // 只要情绪背景,不要指针视差(手机用手势)
    cur = pickStart(visited); render('today');
    $('#diceBtn').onclick = dice;
    $('#infoBtn').onclick = toggleInfo;
    // 体感(iOS 需点一下授权)
    $('#motionBtn').onclick = async () => {
      try {
        if (typeof DeviceMotionEvent !== 'undefined' && typeof DeviceMotionEvent.requestPermission === 'function') { const r = await DeviceMotionEvent.requestPermission(); if (r !== 'granted') return; }
        attachShake(); $('#motionBtn').textContent = '🎲 已开';
      } catch { }
    };
    if (typeof DeviceMotionEvent !== 'undefined' && typeof DeviceMotionEvent.requestPermission !== 'function') attachShake(); // 安卓:直接挂
  } catch (e) { console.error('mobile init error', e); }   // 出错也不影响图例关闭与基本浏览
})();
