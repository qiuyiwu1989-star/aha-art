// 逛法 · 二选一之路 —— 选择即路径,边逛边建口味
import { $, el, esc, loadData, WORKS, BY, bump, rankedNeighbors, pickStart, topThemes, artframe, thumbImg } from './core.js';

const ROUNDS = 8;
let champ = null, chal = null, picks = [], used = new Set();
const left = $('#vsLeft'), right = $('#vsRight'), trail = $('#vsTrail'), summary = $('#vsSummary');

function pickChallenger(exclude) {
  const nbs = rankedNeighbors(champ).map(n => n.to).filter(s => s !== exclude && !used.has(s));
  if (nbs.length) return nbs[Math.floor(Math.random() * Math.min(nbs.length, 4))];
  const rest = WORKS.map(w => w.slug).filter(s => s !== champ && s !== exclude && !used.has(s));
  return rest.length ? rest[Math.floor(Math.random() * rest.length)] : WORKS[0].slug;
}
function renderHalf(box, slug) {
  box.querySelectorAll('.artframe,.vcap').forEach(n => n.remove());
  const w = BY[slug];
  box.insertBefore(artframe(w, 'dissolve'), box.firstChild);
  box.appendChild(el(`<div class="vcap">《${esc(w.title)}》 · ${esc(w.artist || '')}</div>`));
}
function renderTrail() {
  trail.innerHTML = '';
  picks.slice(-8).forEach(s => { const t = el(`<div class="vt"></div>`); t.appendChild(thumbImg(BY[s])); trail.appendChild(t); });
  if (picks.length) trail.appendChild(el(`<span class="vtmore">已选 ${picks.length} / ${ROUNDS}</span>`));
}
function round() {
  renderHalf(left, champ); renderHalf(right, chal); renderTrail();
}
function choose(winner, loser) {
  champ = winner; picks.push(winner); used.add(winner); used.add(loser);
  bump(BY[winner].themes, 2); bump(BY[loser].themes, -0.3);
  if (picks.length >= ROUNDS) return finish();
  chal = pickChallenger(winner); round();
}
function finish() {
  const tt = topThemes(3);
  summary.querySelector('.vsthemes').innerHTML = tt.map(t => '#' + esc(t)).join(' &nbsp; ');
  summary.classList.add('open');
}
(async () => {
  await loadData();
  champ = pickStart(); used.add(champ); chal = pickChallenger(champ); round();
  left.onclick = () => choose(champ, chal);
  right.onclick = () => choose(chal, champ);
  summary.querySelector('button').onclick = () => location.reload();
})();
