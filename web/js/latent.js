// 概念 2 · 审美潜空间 —— 拖着维度,在整片人类名作里飞行
import { $, $$, el, esc, loadData, WORKS, BY, topThemes, artframe, thumbImg } from './core.js';

// 人工赋的审美维度(0–1)。日后由你们的打标语料替换、扩到全库。
const DIMS = {
  'paris-rainy': { light: .5, energy: .35, warm: .35, order: .8 },
  'grande-jatte': { light: .7, energy: .25, warm: .55, order: .9 },
  'vg-bedroom': { light: .6, energy: .5, warm: .6, order: .45 },
  'waterlilies': { light: .6, energy: .3, warm: .5, order: .3 },
  'haystacks': { light: .7, energy: .3, warm: .7, order: .5 },
  'two-sisters': { light: .8, energy: .4, warm: .75, order: .5 },
  'basket-apples': { light: .55, energy: .3, warm: .6, order: .65 },
  'great-wave': { light: .6, energy: .95, warm: .3, order: .7 },
  'childs-bath': { light: .65, energy: .3, warm: .6, order: .7 },
  'moulin-rouge': { light: .35, energy: .55, warm: .45, order: .45 },
  'el-greco-assump': { light: .45, energy: .85, warm: .3, order: .25 },
  'gauguin-day': { light: .6, energy: .5, warm: .6, order: .55 },
  'vg-selfportrait': { light: .5, energy: .8, warm: .55, order: .35 },
  'hiroshige': { light: .4, energy: .2, warm: .4, order: .85 },
  'monet-cliff': { light: .75, energy: .5, warm: .45, order: .4 },
  'seurat-study': { light: .6, energy: .3, warm: .55, order: .55 },
  'renoir-lunch': { light: .8, energy: .45, warm: .75, order: .45 },
  'toulouse-jane': { light: .45, energy: .5, warm: .5, order: .55 },
};
const AX = {
  light: ['暗', '明'], energy: ['静', '动'], warm: ['冷', '暖'], vivid: ['淡', '艳'], year: ['早', '晚'],
};
const NAME = { light: '明暗', energy: '动静', warm: '冷暖', vivid: '鲜艳', year: '年代' };
const warmth = h => (Math.cos((h - 40) * Math.PI / 180) + 1) / 2;
let xKey = 'energy', yKey = 'light';
const plot = $('#plot'), xg = $('#xaxis'), yg = $('#yaxis');

function val(w, key) {
  if (key === 'year') { const ys = WORKS.map(x => x.year || 0); const mn = Math.min(...ys), mx = Math.max(...ys); return ((w.year || mn) - mn) / (mx - mn || 1); }
  const c = w.color && w.color.hsl, m = w.mood;       // 从数据读维度,自适应全样本
  if (key === 'light') return c ? c[2] : .5;
  if (key === 'vivid') return c ? c[1] : .5;
  if (key === 'warm') return c ? warmth(c[0]) : .5;
  if (key === 'energy') return m ? m.arousal : .5;
  return .5;
}
function render() {
  $$('button', xg).forEach(b => b.classList.toggle('on', b.dataset.k === xKey));
  $$('button', yg).forEach(b => b.classList.toggle('on', b.dataset.k === yKey));
  plot.querySelectorAll('.dot,.you,.axlabel').forEach(n => n.remove());
  plot.appendChild(el(`<div class="axlabel ax-x">${NAME[xKey]} · ${AX[xKey][1]} →</div>`));
  plot.appendChild(el(`<div class="axlabel ax-x0">← ${AX[xKey][0]}</div>`));
  plot.appendChild(el(`<div class="axlabel ax-y">↑ ${NAME[yKey]} · ${AX[yKey][1]}</div>`));
  plot.appendChild(el(`<div class="axlabel ax-y0">${AX[yKey][0]}</div>`));
  WORKS.forEach(w => {
    const x = 6 + val(w, xKey) * 88, y = 6 + (1 - val(w, yKey)) * 84;
    const d = el(`<div class="dot" style="left:${x}%;top:${y}%"><span class="dlab">${esc(w.artist || w.title)}</span></div>`);
    d.insertBefore(thumbImg(w), d.firstChild);
    d.onclick = () => location.href = `index.html`; // 进经典版漫游(共享口味)
    plot.appendChild(d);
  });
  // 你的审美落点:与你口味相关的作品的维度质心
  const top = topThemes(6);
  const mine = WORKS.filter(w => (w.themes || []).some(t => top.includes(t)));
  if (mine.length) {
    const ax = mine.reduce((s, w) => s + val(w, xKey), 0) / mine.length;
    const ay = mine.reduce((s, w) => s + val(w, yKey), 0) / mine.length;
    plot.appendChild(el(`<div class="you" style="left:${6 + ax * 88}%;top:${6 + (1 - ay) * 84}%">✦ 你的审美落点</div>`));
  }
}
(async () => {
  await loadData();
  Object.keys(NAME).forEach(k => {
    xg.appendChild(Object.assign(el(`<button data-k="${k}">${NAME[k]}</button>`), { onclick: () => { xKey = k; render(); } }));
    yg.appendChild(Object.assign(el(`<button data-k="${k}">${NAME[k]}</button>`), { onclick: () => { yKey = k; render(); } }));
  });
  render();
})();
