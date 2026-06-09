// 逛法 · 对话策展 —— 说一句心情/愿望,它端画上来并讲为何
import { $, el, esc, loadData, WORKS, BY, bump, matchedThemes, artframe } from './core.js';

const log = $('#chatlog'), input = $('#talkInput'), sendBtn = $('#sendBtn'), chips = $('#chips');

// 关键词 → 母题(细粒度打标语料可替换/扩展此表)
const DICT = [
  [/悲伤|难过|忧郁|哀|失落/, ['孤独', '疏离', '情感强度']],
  [/希望|治愈|温暖|慰藉/, ['温情', '明媚', '光']],
  [/孤独|寂寞|独处/, ['孤独', '疏离', '私密']],
  [/平静|安静|宁静|放松|静下来/, ['宁静', '沉思', '自然']],
  [/明亮|明媚|阳光|开朗/, ['明媚', '光', '休闲']],
  [/壮丽|崇高|震撼|宏大|力量/, ['崇高', '自然之力', '海']],
  [/热闹|夜|喧嚣|人多|派对/, ['夜生活', '人群', '现代']],
  [/爱|温柔|亲密|思念/, ['温情', '母与子', '私密']],
  [/自然|海|山|水|风|户外/, ['自然', '海', '水', '风']],
  [/光|光影|发光/, ['光', '光影']],
  [/秩序|理性|结构|专注|工作/, ['秩序', '结构', '沉思']],
  [/灵性|神圣|宗教|超越|信仰/, ['灵性', '升腾', '宗教']],
  [/东方|禅|诗意|月/, ['东方', '诗意', '月']],
  [/焦虑|烦躁|不安|紧张/, ['情感强度', '扭曲的形']],
  [/都市|城市|现代|生活/, ['都市', '现代生活', '疏离']],
];
function infer(text) {
  const hit = new Set();
  DICT.forEach(([re, ts]) => { if (re.test(text)) ts.forEach(t => hit.add(t)); });
  if (!hit.size) ['光', '宁静', '色彩'].forEach(t => hit.add(t)); // 兜底
  return [...hit];
}
function recommend(themes) {
  return WORKS.map(w => ({ w, s: (w.themes || []).filter(t => themes.includes(t)).length }))
    .filter(x => x.s > 0).sort((a, b) => b.s - a.s).slice(0, 3).map(x => x.w);
}
function scroll() { log.scrollTop = log.scrollHeight; }
function me(text) { log.appendChild(el(`<div class="msg me">${esc(text)}</div>`)); scroll(); }
function ai(text, works, themes) {
  const wrap = el(`<div class="msg ai"><div class="ai-say">${esc(text)}</div><div class="ai-cards"></div></div>`);
  const cards = wrap.querySelector('.ai-cards');
  works.forEach(w => {
    const overlap = (w.themes || []).filter(t => themes.includes(t)).slice(0, 2);
    const card = el(`<div class="ai-card"><div class="acimg"><img src="${w.lqip}" alt=""/></div>
      <div class="act">《${esc(w.title)}》</div>
      <div class="acw">${esc(w.artist || '')}${overlap.length ? ' · ' + overlap.map(t => '#' + t).join(' ') : ''}</div></div>`);
    card.querySelector('.acimg img').src = w.image;
    card.querySelector('.acimg img').onerror = function () { this.style.display = 'none'; };
    card.onclick = () => { bump(w.themes, 1.5); detail(w); };
    cards.appendChild(card);
  });
  log.appendChild(wrap); scroll();
}
function detail(w) {
  ai(`《${w.title}》—— ${w.oneLiner}  👁 ${w.look}`, [], []);
}
function ask(text) {
  if (!text.trim()) return;
  me(text);
  const themes = infer(text), works = recommend(themes);
  themes.forEach(t => bump([t], 0.6));
  const lead = works.length
    ? `听起来你想要 ${themes.slice(0, 2).map(t => '「' + t + '」').join('、')} 的东西。这几幅,或许正合此刻 —`
    : `我还没太抓住那种感觉,换个说法试试?比如"安静下来"、"壮丽一点"、"像悲伤但有希望"。`;
  setTimeout(() => ai(lead, works, themes), 280);
}
(async () => {
  await loadData();
  ['像悲伤但有一点希望', '让我安静下来', '壮丽、震撼', '热闹的夜', '东方的诗意', '专注工作时'].forEach(q => {
    const c = el(`<button class="tchip">${q}</button>`); c.onclick = () => ask(q); chips.appendChild(c);
  });
  ai('你此刻想要一种什么样的画?跟我说说感觉就好 —— 比如心情、场景,或想成为的状态。', [], []);
  sendBtn.onclick = () => { ask(input.value); input.value = ''; };
  input.addEventListener('keydown', e => { if (e.key === 'Enter') { ask(input.value); input.value = ''; } });
})();
