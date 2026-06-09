// 概念 4 · 策展台 —— 人人都是策展人,攒一个个展并分享
import { $, $$, el, esc, loadData, WORKS, BY, artframe } from './core.js';

const MAX = 7;
const grid = $('#curGrid'), tray = $('#tray'), titleIn = $('#exTitle'),
  countEl = $('#tcount'), buildBtn = $('#buildBtn'), stage = $('#curStage'), exhibit = $('#exhibit');
let picked = [];

function syncTray() {
  countEl.textContent = `${picked.length} / ${MAX} 幅`;
  buildBtn.disabled = picked.length < 2;
  $$('.mini', grid).forEach(m => m.classList.toggle('picked', picked.includes(m.dataset.slug)));
}
function toggle(slug) {
  const i = picked.indexOf(slug);
  if (i >= 0) picked.splice(i, 1);
  else { if (picked.length >= MAX) return; picked.push(slug); }
  syncTray();
}
function renderExhibit(slugs, title, shared) {
  stage.style.display = 'none'; tray.style.display = 'none'; exhibit.style.display = 'block';
  exhibit.innerHTML = `<div class="ex-title">${esc(title || '无题')}</div>
    <div class="ex-by">一个由你策展的小型个展 · ${slugs.length} 幅${shared ? ' · 有人分享给你' : ''}</div>
    <div class="ex-wall"></div>
    <div class="ex-actions">
      <button id="exShare">复制分享链接</button>
      <button id="exNew">${shared ? '我也策一个 →' : '继续修改'}</button>
    </div>`;
  const wall = $('.ex-wall', exhibit);
  slugs.forEach(s => {
    const w = BY[s]; if (!w) return;
    const c = el(`<div class="ex-w"></div>`); c.appendChild(artframe(w));
    c.appendChild(el(`<div class="ex-cap">《${esc(w.title)}》 · ${esc(w.artist || '')}</div>`));
    wall.appendChild(c);
  });
  $('#exShare', exhibit).onclick = () => {
    const url = location.origin + location.pathname + '#room=' + slugs.join(',') + '&t=' + encodeURIComponent(title || '');
    (navigator.clipboard?.writeText(url)) ? alert('已复制分享链接:\n\n' + url) : prompt('复制此链接:', url);
  };
  $('#exNew', exhibit).onclick = () => { location.hash = ''; location.reload(); };
}
function parseHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  const room = h.get('room'); if (!room) return null;
  return { slugs: room.split(',').filter(s => BY[s]), title: h.get('t') || '' };
}
(async () => {
  await loadData();
  const shared = parseHash();
  if (shared && shared.slugs.length) { renderExhibit(shared.slugs, shared.title, true); return; }
  WORKS.forEach(w => {
    const m = el(`<div class="mini" data-slug="${w.slug}"></div>`);
    m.appendChild(artframe(w));
    m.appendChild(el(`<div class="cap">${esc(w.artist || w.title)}</div>`));
    m.onclick = () => toggle(w.slug);
    grid.appendChild(m);
  });
  buildBtn.onclick = () => { if (picked.length >= 2) renderExhibit(picked, titleIn.value.trim(), false); };
  syncTray();
})();
