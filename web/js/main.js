// ═══ aha · 控制器 v2 ═══
// 画来找人 / 顺着门走 / 被懂的理由 / 你的星座。纯前端,客户端个性化。

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const el = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstChild; };
const esc = (s) => String(s || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ── 数据 ──
let WORKS = [], GRAPH = null, BY = {}, ADJ = {}, TYPE_LABEL = {};
// ── 状态 ──
const LS = 'aha.taste.v1';
let taste = JSON.parse(localStorage.getItem(LS) || '{}');
let visited = new Set(), loved = new Set(), journey = [];
let doorsFollowed = 0, hearts = 0, view = 'boot';
// 当前漫游页的快捷操作引用(键盘用)
let curToggleInfo = null, curHeart = null, curDoors = [], curRandom = null, curBack = null;

async function boot() {
  try {
    [WORKS, GRAPH] = await Promise.all([
      fetch('data/artworks.json').then(r => r.json()),
      fetch('data/graph.json').then(r => r.json()),
    ]);
  } catch (e) { $('#boot').textContent = '数据加载失败:请用本地服务器打开(见 README)。'; return; }
  WORKS.forEach(w => { BY[w.slug] = w; ADJ[w.slug] = []; });
  GRAPH.edges.forEach(e => {
    ADJ[e.a].push({ to: e.b, type: e.type, why: e.why });
    ADJ[e.b].push({ to: e.a, type: e.type, why: e.why });
  });
  TYPE_LABEL = GRAPH.typeLabels;
  $('#boot').classList.add('gone');
  $('#brandBtn').onclick = () => goToday();
  $('#starBtn').onclick = renderStar;
  document.addEventListener('keydown', onKey);
  if (Object.keys(taste).length) goToday();
  else renderOnboard();
  updateMeta();
}

function goToday() { journey = []; renderRoam(pickStart(), { kind: 'today' }); }
function updateMeta() {
  $('#topMeta').textContent = visited.size
    ? `已遇见 ${visited.size} · 心动 ${hearts} · 推开 ${doorsFollowed} 扇门` : '';
}
function bump(themes, w) { (themes || []).forEach(t => taste[t] = (taste[t] || 0) + w); save(); }
function save() { localStorage.setItem(LS, JSON.stringify(taste)); }
function score(work) { return (work.themes || []).reduce((s, t) => s + (taste[t] || 0), 0); }
function topThemes(n = 4) {
  return Object.entries(taste).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, n).map(x => x[0]);
}

// ── 可加载图(blur-up + 失败降级 + 一次降尺寸重试)──
function artframe(work, cls = '') {
  const f = el(`<div class="artframe ${cls}">
    <img class="blur" src="${work.lqip || ''}" alt="" aria-hidden="true"/>
    <img class="full" alt="${esc(work.alt || work.title)}"/>
    <div class="fallback"><div class="ft">《${esc(work.title)}》</div>
      <div class="fa">${esc(work.artist || '')}</div><div class="fn">${esc(work.date || '')}</div></div>
  </div>`);
  const full = $('.full', f);
  let retried = false;
  full.onload = () => full.classList.add('loaded');
  full.onerror = () => {
    if (!retried && /\/\d+,\//.test(work.image)) { retried = true; full.src = work.image.replace(/\/\d+,\//, '/600,/'); }
    else f.classList.add('failed');
  };
  full.src = work.image;
  return f;
}

// 键盘:漫游页快捷键
function onKey(e) {
  if (view !== 'roam') return;
  if (e.key === 'i' || e.key === 'I') { curToggleInfo && curToggleInfo(); }
  else if (e.key === 'h' || e.key === 'H') { curHeart && curHeart(); }
  else if (e.key === 'r' || e.key === 'R') { curRandom && curRandom(); }
  else if (e.key === 'ArrowLeft') { curBack && curBack(); }
  else if (['1', '2', '3'].includes(e.key)) { const d = curDoors[+e.key - 1]; d && d(); }
}

// ═══ 冷启动:审美滑滑 ═══
const OB_SEQ = ['great-wave', 'vg-selfportrait', 'waterlilies', 'paris-rainy', 'el-greco-assump',
  'childs-bath', 'grande-jatte', 'hiroshige', 'moulin-rouge', 'basket-apples'];
function renderOnboard() {
  view = 'onboard'; let i = 0;
  const v = $('#view'); v.innerHTML = '';
  const wrap = el(`<div class="onboard fade-in">
    <div class="ob-head"><div class="ob-kicker">先认识一下你的眼睛</div>
      <div class="ob-h">哪些,让你想多看一眼?</div>
      <div class="ob-sub">凭直觉就好 —— 30 秒,让 aha 懂你的口味。</div></div>
    <div class="ob-card"><div class="ob-art-holder"></div>
      <div class="ob-cap"></div><div class="ob-progress"></div>
      <div class="ob-actions">
        <button class="ob-btn skip" title="无感">✕</button>
        <button class="ob-btn like" title="想多看一眼">♥</button></div>
      <div class="ob-hint">✕ 无感 &nbsp;·&nbsp; ♥ 想多看一眼</div>
      <button class="ob-skipall">直接开始漫游 →</button></div></div>`);
  v.appendChild(wrap);
  const holder = $('.ob-art-holder', wrap), cap = $('.ob-cap', wrap), prog = $('.ob-progress', wrap);
  function show() {
    if (i >= OB_SEQ.length) return finishOnboard();
    const w = BY[OB_SEQ[i]];
    holder.innerHTML = ''; const a = artframe(w, 'ob-art fade-in'); holder.appendChild(a);
    cap.textContent = w.artist; prog.textContent = `${i + 1} / ${OB_SEQ.length}`;
  }
  function choose(like) {
    const w = BY[OB_SEQ[i]];
    const card = $('.ob-art', wrap);
    if (card) card.style.transform = like ? 'translateX(40px) rotate(3deg)' : 'translateX(-40px) rotate(-3deg)';
    bump(w.themes, like ? 2 : -0.4); if (like) visited.add(w.slug);
    i++; setTimeout(show, 130);
  }
  $('.like', wrap).onclick = () => choose(true);
  $('.skip', wrap).onclick = () => choose(false);
  $('.ob-skipall', wrap).onclick = finishOnboard;
  show();
}
function finishOnboard() {
  if (!Object.keys(taste).length) WORKS.forEach(w => bump(w.themes, 0.1));
  goToday(); updateMeta();
}

// ═══ 漫游 ═══
function pickStart() {
  const unseen = WORKS.filter(w => !visited.has(w.slug));
  return (unseen.length ? unseen : WORKS).slice().sort((a, b) => score(b) - score(a))[0].slug;
}
function rankDoors(slug) {
  const from = journey[journey.length - 2] || null;
  let nb = ADJ[slug].filter(d => d.to !== from); if (!nb.length) nb = ADJ[slug].slice();
  const bt = {}; nb.forEach(d => { if (!bt[d.to]) bt[d.to] = d; });
  let list = Object.values(bt).map(d => ({ ...d, s: score(BY[d.to]) })).sort((a, b) => b.s - a.s);
  if (list.length <= 3) return list.map(d => ({ ...d, explore: false }));
  return [...list.slice(0, 2).map(d => ({ ...d, explore: false })), { ...list[list.length - 1], explore: true }];
}
// 「为你而来」理由
function reasonHTML(work, reason) {
  const matched = (work.themes || []).filter(t => topThemes(6).includes(t)).slice(0, 2);
  if (reason.kind === 'today')
    return `<div class="reason">✦ 为你而来 · 今天最贴你的一帧${matched.length ? ' · 因为你偏爱 ' + matched.map(t => '#' + esc(t)).join(' ') : ''}</div>`;
  if (reason.kind === 'taste' && matched.length)
    return `<div class="reason">为你而来 · 因为你偏爱 ${matched.map(t => '#' + esc(t)).join(' ')}</div>`;
  if (reason.kind === 'explore')
    return `<div class="reason explore">踮脚一张 · 你舒适区之外的风景</div>`;
  if (reason.kind === 'random')
    return `<div class="reason">不期而遇 · 随手推开的一扇门</div>`;
  return '';
}

function renderRoam(slug, reason = { kind: 'today' }, isBack = false) {
  view = 'roam';
  const w = BY[slug];
  if (!isBack && journey[journey.length - 1] !== slug) journey.push(slug);
  visited.add(slug); updateMeta();
  const v = $('#view'); v.innerHTML = '';
  const isLoved = loved.has(slug);
  const root = el(`<div class="roam fade-in"><div class="work-wrap">
    <div class="roam-nav">
      <button class="rn-btn back" ${journey.length > 1 ? '' : 'disabled'} title="上一幅 (←)">← 上一幅</button>
      <div class="journey-dots"></div>
      <button class="rn-btn random" title="不期而遇 (R)">✦ 不期而遇</button>
    </div>
    ${reasonHTML(w, reason)}
    <div class="art-holder"></div>
    <div class="tap-hint">轻点画面 · 读它 &nbsp;(I)</div>
    <div class="work-info"><div class="wi-inner">
      <div class="wi-title">《${esc(w.title)}》</div>
      <div class="wi-by">${esc(w.artist || '')} · ${esc(w.date || '')}</div>
      <div class="wi-one">${esc(w.oneLiner)}</div>
      <div class="wi-look">👁 <b>看这里</b> — ${esc(w.look)}</div>
      <div class="wi-themes">${(w.themes || []).map(t => `<span class="t">${esc(t)}</span>`).join('')}</div>
    </div></div>
    <div class="heart-row"><button class="heart ${isLoved ? 'on' : ''}"><span class="hi">${isLoved ? '♥' : '♡'}</span><span class="ht">${isLoved ? '已心动' : '心动'}</span></button></div>
    <div class="doors"><div class="doors-label">顺着这幅画走 —— 推开一扇门</div><div class="doors-list"></div></div>
    <div class="kbd-hint">键盘:1·2·3 推开门 &nbsp; I 读它 &nbsp; H 心动 &nbsp; R 不期而遇 &nbsp; ← 上一幅</div>
  </div></div>`);
  v.appendChild(root);

  // 旅程小点
  const dots = $('.journey-dots', root);
  journey.slice(-7).forEach((s, idx, arr) => {
    const d = el(`<span class="jd ${s === slug ? 'now' : ''}" title="${esc(BY[s].title)}"></span>`);
    dots.appendChild(d);
  });

  // 画 + 轻点浮现
  const holder = $('.art-holder', root); const af = artframe(w, 'work-art'); holder.appendChild(af);
  const info = $('.work-info', root), hint = $('.tap-hint', root);
  curToggleInfo = () => { info.classList.toggle('open'); hint.classList.add('hide'); };
  af.onclick = curToggleInfo;

  // 心动
  const heart = $('.heart', root);
  curHeart = () => {
    if (loved.has(slug)) { loved.delete(slug); heart.classList.remove('on'); $('.hi', heart).textContent = '♡'; $('.ht', heart).textContent = '心动'; }
    else { loved.add(slug); hearts++; heart.classList.add('on'); $('.hi', heart).textContent = '♥'; $('.ht', heart).textContent = '已心动'; bump(w.themes, 2); heart.classList.add('pulse'); setTimeout(() => heart.classList.remove('pulse'), 400); }
    updateMeta();
  };
  heart.onclick = curHeart;
  if (!loved.has(slug)) bump(w.themes, 0.3);

  // 门
  const dl = $('.doors-list', root); curDoors = [];
  rankDoors(slug).forEach((d, idx) => {
    const door = el(`<button class="door ${d.explore ? 'explore' : ''}">
      <div class="door-top"><span class="door-key">${idx + 1}</span>
        <span class="door-chip">${d.explore ? '探索 ✦' : esc(TYPE_LABEL[d.type] || d.type)}</span>
        <span class="door-arrow">→</span></div>
      <div class="door-why">${esc(d.why)}</div></button>`);
    const open = () => {
      doorsFollowed++; bump(BY[d.to].themes, 1);
      transitionTo(() => renderRoam(d.to, { kind: d.explore ? 'explore' : 'taste' }));
    };
    door.onclick = open; curDoors[idx] = open;
    dl.appendChild(door);
  });

  // 上一幅 / 不期而遇
  curBack = () => { if (journey.length > 1) { journey.pop(); transitionTo(() => renderRoam(journey[journey.length - 1], { kind: 'back' }, true)); } };
  curRandom = () => {
    const unseen = WORKS.filter(x => !visited.has(x.slug));
    const pool = unseen.length ? unseen : WORKS.filter(x => x.slug !== slug);
    const pick = pool[Math.floor(Math.random() * pool.length)];
    journey = []; transitionTo(() => renderRoam(pick.slug, { kind: 'random' }));
  };
  $('.back', root).onclick = curBack;
  $('.random', root).onclick = curRandom;

  window.scrollTo({ top: 0 });
}

// 轻过渡(淡出 → 重渲染 → 淡入)
function transitionTo(fn) {
  const v = $('#view'); v.classList.add('leaving');
  setTimeout(() => { v.classList.remove('leaving'); fn(); }, 180);
}

// ═══ 星座 / 审美画像 ═══
const THEME_BLURB = {
  '孤独': '你被独处与疏离打动', '疏离': '你对人群中的孤独敏感', '光': '你追逐光', '宁静': '你向往安静',
  '自然': '你亲近自然', '色彩': '你被纯粹的色彩吸引', '都市': '你着迷于现代都市', '私密': '你珍视私密的时刻',
  '温情': '你被温柔打动', '情感强度': '你偏爱强烈的情感', '灵性': '你被超越性的东西吸引', '东方': '你偏爱东方的诗意',
  '秩序': '你欣赏结构与秩序', '现代生活': '你关注现代生活', '海': '你被海与水打动', '沉思': '你喜欢沉思的画面',
};
function constellationSVG(seen) {
  const n = seen.length, size = Math.max(360, Math.min(760, 260 + n * 24));
  const cx = size / 2, cy = size / 2, C = (size / 2) / Math.sqrt(Math.max(n, 1)) * 0.86;
  const pos = {};
  seen.forEach((w, i) => { const a = i * 2.399963; const r = i === 0 ? 0 : C * Math.sqrt(i + 0.5); pos[w.slug] = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }; });
  const seenSet = new Set(seen.map(w => w.slug)); const drawn = new Set(); let lines = '';
  GRAPH.edges.forEach(e => {
    if (seenSet.has(e.a) && seenSet.has(e.b)) {
      const k = [e.a, e.b].sort().join('|'); if (drawn.has(k)) return; drawn.add(k);
      const p = pos[e.a], q = pos[e.b]; lines += `<line x1="${p.x}" y1="${p.y}" x2="${q.x}" y2="${q.y}" class="cl"/>`;
    }
  });
  let pl = '';
  for (let i = 1; i < journey.length; i++) { const p = pos[journey[i - 1]], q = pos[journey[i]]; if (p && q) pl += `<line x1="${p.x}" y1="${p.y}" x2="${q.x}" y2="${q.y}" class="cl path"/>`; }
  let nodes = '';
  seen.forEach((w, i) => {
    const p = pos[w.slug], r = loved.has(w.slug) ? 24 : 17, id = 'cc' + i;
    nodes += `<g class="cnode-svg ${loved.has(w.slug) ? 'loved' : ''}" data-slug="${w.slug}" transform="translate(${p.x},${p.y})">
      <clipPath id="${id}"><circle r="${r}"/></clipPath>
      <image href="${w.lqip}" x="${-r}" y="${-r}" width="${2 * r}" height="${2 * r}" clip-path="url(#${id})" preserveAspectRatio="xMidYMid slice"/>
      <circle r="${r}" class="ring"/></g>`;
  });
  return `<svg viewBox="0 0 ${size} ${size}" class="constellation-svg" preserveAspectRatio="xMidYMid meet">${lines}${pl}${nodes}</svg>`;
}
function renderStar() {
  view = 'star';
  const v = $('#view'); v.innerHTML = '';
  const seen = WORKS.filter(w => visited.has(w.slug));
  const tt = topThemes(4);
  const portrait = tt.length
    ? '你的审美,关于 ' + tt.map(t => `<b>${esc(t)}</b>`).join('、') + '。<br/>' +
    (tt.map(t => THEME_BLURB[t]).filter(Boolean).slice(0, 2).join('、') || '你正在长出自己的眼睛') + '。'
    : '多看几幅、推开几扇门,你的审美就会在这里显形。';
  const root = el(`<div class="star fade-in">
    <div class="star-kicker">Your Constellation · 你的星座</div>
    <div class="star-h">这就是你的审美</div>
    <div class="star-portrait">${portrait}</div>
    <div class="star-stats">遇见 ${seen.length} 幅 · 心动 ${loved.size} 次 · 推开 ${doorsFollowed} 扇门</div>
    <div class="star-themes">${tt.map(t => `<span class="st">#${esc(t)}</span>`).join('')}</div>
    ${seen.length ? `<div class="constel-wrap">${constellationSVG(seen)}</div>
      <div class="constel-legend">每颗星是你遇见的一幅画 · 细线是它们在艺术史中的关联 · <span class="lg-path">高亮</span>是你走过的路</div>`
      : '<div class="star-empty">你还没遇见任何作品 —— 去漫游吧。</div>'}
    <button class="star-back">继续漫游 →</button>
    <button class="star-share">把我的审美星座分享出去</button></div>`);
  v.appendChild(root);
  $$('.cnode-svg', root).forEach(g => g.onclick = () => { journey = []; transitionTo(() => renderRoam(g.dataset.slug, { kind: 'star' })); });
  $('.star-back', root).onclick = () => goToday();
  $('.star-share', root).onclick = () => {
    const txt = `我的 aha 审美星座:关于 ${tt.join('、')} —— 遇见 ${seen.length} 幅名作,心动 ${loved.size} 次。`;
    if (navigator.share) navigator.share({ title: 'aha 审美星座', text: txt }).catch(() => { });
    else { navigator.clipboard?.writeText(txt); alert('已复制你的审美星座文案:\n\n' + txt); }
  };
  window.scrollTo({ top: 0 });
}

boot();
