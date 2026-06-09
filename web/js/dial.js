// 逛法 · 情绪方向盘 —— 连续掌舵,在审美空间里"开"
import { $, el, esc, loadData, WORKS, BY, artframe } from './core.js';
import { initAmbient } from './ambient.js';

// 与潜空间一致的人工维度(0–1);日后由打标语料替换
const DIMS = {
  'paris-rainy': { e: .35, l: .5, w: .35 }, 'grande-jatte': { e: .25, l: .7, w: .55 }, 'vg-bedroom': { e: .5, l: .6, w: .6 },
  'waterlilies': { e: .3, l: .6, w: .5 }, 'haystacks': { e: .3, l: .7, w: .7 }, 'two-sisters': { e: .4, l: .8, w: .75 },
  'basket-apples': { e: .3, l: .55, w: .6 }, 'great-wave': { e: .95, l: .6, w: .3 }, 'childs-bath': { e: .3, l: .65, w: .6 },
  'moulin-rouge': { e: .55, l: .35, w: .45 }, 'el-greco-assump': { e: .85, l: .45, w: .3 }, 'gauguin-day': { e: .5, l: .6, w: .6 },
  'vg-selfportrait': { e: .8, l: .5, w: .55 }, 'hiroshige': { e: .2, l: .4, w: .4 }, 'monet-cliff': { e: .5, l: .75, w: .45 },
  'seurat-study': { e: .3, l: .6, w: .55 }, 'renoir-lunch': { e: .45, l: .8, w: .75 }, 'toulouse-jane': { e: .5, l: .45, w: .5 },
};
let amb = null, cur = null;
const artBox = $('#dialArt'), nowEl = $('#dialNow'), pad = $('#pad'), handle = $('#padHandle'), drive = $('#driveLabel');

function dimsOf(w) { const c = w.color && w.color.hsl, m = w.mood; return { e: m ? m.arousal : .5, l: c ? c[2] : .5 }; } // 从数据读维度
function nearest(ex, ly) {
  let best = null, bd = 1e9;
  WORKS.forEach(w => { const d = dimsOf(w); const dist = (d.e - ex) ** 2 + (d.l - ly) ** 2; if (dist < bd) { bd = dist; best = w; } });
  return best;
}
function showWork(w) {
  if (w.slug === cur) return; cur = w.slug;
  artBox.querySelectorAll('.artframe').forEach(n => { n.classList.add('fade-out'); setTimeout(() => n.remove(), 240); });
  const af = artframe(w, 'dissolve'); artBox.appendChild(af);
  nowEl.textContent = `${w.artist || ''} · ${w.date || ''} —— 《${w.title}》`;
  if (amb) { amb.setMood(w); amb.breathe(true); }
}
function moveTo(ex, ly) {
  handle.style.left = ex * 100 + '%'; handle.style.top = (1 - ly) * 100 + '%';
  drive.textContent = `你正驶向:${ex > .55 ? '动' : ex < .45 ? '静' : '中'} · ${ly > .55 ? '明' : ly < .45 ? '暗' : '中'}`;
  showWork(nearest(ex, ly));
}
function fromEvent(e) {
  const r = pad.getBoundingClientRect();
  const ex = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  const ly = Math.max(0, Math.min(1, 1 - (e.clientY - r.top) / r.height));
  moveTo(ex, ly);
}
(async () => {
  await loadData();
  amb = initAmbient(document.querySelector('.stage'), artBox);
  let down = false;
  pad.addEventListener('pointerdown', e => { down = true; pad.setPointerCapture(e.pointerId); fromEvent(e); });
  pad.addEventListener('pointermove', e => { if (down) fromEvent(e); });
  addEventListener('pointerup', () => down = false);
  moveTo(.5, .55); // 起步:稍偏明、居中
})();
