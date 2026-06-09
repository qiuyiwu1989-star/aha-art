// 逛法 · 以色觅画 —— 吸一个颜色,顺着它找画
import { $, $$, el, esc, loadData, WORKS, artframe, thumbImg } from './core.js';
import { ambientColor } from './ambient.js';

const palette = $('#palette'), grid = $('#cgrid'), pickNow = $('#pickNow');
let C = {}, pick = null;

function rgb2hsl([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b); let h, s, l = (mx + mn) / 2;
  if (mx === mn) { h = s = 0; }
  else { const d = mx - mn; s = l > .5 ? d / (2 - mx - mn) : d / (mx + mn);
    h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; h /= 6; }
  return [h * 360, s, l];
}
function dist(a, b) { let dh = Math.abs(a[0] - b[0]); dh = Math.min(dh, 360 - dh) / 180; return dh * 2 + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]) * .8; }

function setPick(slug) {
  pick = C[slug];
  $$('.sw', palette).forEach(s => s.classList.toggle('on', s.dataset.slug === slug));
  const [r, g, b] = pick.rgb;
  document.body.style.backgroundColor = `rgb(${(r * .26) | 0},${(g * .26) | 0},${(b * .28) | 0})`;
  const sorted = WORKS.slice().sort((x, y) => dist(C[x.slug].hsl, pick.hsl) - dist(C[y.slug].hsl, pick.hsl));
  grid.innerHTML = '';
  sorted.forEach((w, i) => {
    const tile = el(`<div class="cg ${i === 0 ? 'top' : ''}"><div class="cgc">${esc(w.artist || w.title)}</div></div>`);
    tile.insertBefore(thumbImg(w), tile.firstChild);
    tile.style.borderColor = `rgb(${C[w.slug].rgb.join(',')})`;
    tile.onclick = () => setPick(w.slug);
    grid.appendChild(tile);
  });
  pickNow.textContent = '正顺着这抹色 · 点任意一幅,顺它的颜色继续往下走';
}
(async () => {
  await loadData();
  const cols = await Promise.all(WORKS.map(w => ambientColor(w)));
  WORKS.forEach((w, i) => C[w.slug] = { rgb: cols[i], hsl: rgb2hsl(cols[i]) });
  // 调色板:按色相排成一道彩虹
  WORKS.slice().sort((a, b) => C[a.slug].hsl[0] - C[b.slug].hsl[0]).forEach(w => {
    const sw = el(`<div class="sw" data-slug="${w.slug}" title="${esc(w.title)}"></div>`);
    sw.style.background = `rgb(${C[w.slug].rgb.join(',')})`;
    sw.onclick = () => setPick(w.slug);
    palette.appendChild(sw);
  });
  // 起步:挑最鲜艳的一幅
  const vivid = WORKS.slice().sort((a, b) => C[b.slug].hsl[1] - C[a.slug].hsl[1])[0];
  setPick(vivid.slug);
})();
