// ═══ 美学实验室 · 装置驱动(介绍 → 自适应测评 → 报告)═══
// 测评 = 测量(最大化信息+覆盖),而非推荐:自适应选题 + 变长 + 二选一。
import { Content } from './content.js';
import { Brain } from './brain.js';

const $ = s => document.querySelector(s);
const esc = s => String(s || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const MIN = 8, MAX = 20, STOP_CONF = 0.82;   // 测到清楚为止

let calib = null, seen = new Set(), count = 0, cur = null, shownAt = 0, curPair = null, step = 0;

function show(id) { document.querySelectorAll('.screen').forEach(s => s.classList.remove('on')); $('#' + id).classList.add('on'); window.scrollTo(0, 0); }
function imgInto(holder, w) {
  holder.innerHTML = `<img class="blur" src="${w.lqip || ''}" aria-hidden="true"/><img class="full" alt=""/>`;
  const full = holder.querySelector('.full'); let r = 0;
  full.onload = () => full.classList.add('on');
  full.onerror = () => { if (!r && /\/\d+,\//.test(w.image)) { r = 1; full.src = w.image.replace(/\/\d+,\//, '/800,/'); } };
  full.src = w.image;
}
const pct = x => Math.round(x * 100) + '%';

// ── 一步:决定 单图自适应 还是 二选一 ──────────────
function nextStep() {
  // 停止条件:够多且够清楚,或到上限
  if (count >= MAX || (count >= MIN && Brain.measured() >= STOP_CONF)) { setTimeout(finish, 300); return; }
  step++;
  $('#single').style.display = 'none'; $('#pair').style.display = 'none';
  // 每第 3 步来一次二选一(隔离最不确定的轴)
  if (step % 3 === 0) {
    const p = Brain.probePair({ seen: [...seen] });
    if (p) { curPair = p; const lo = Content.getWork(p.low), hi = Content.getWork(p.high);
      $('#pair').style.display = ''; $('#pairQ').textContent = `哪一张更打动你?`;
      $('#probeHint').textContent = `正在试探:${p.axis}`;
      imgInto($('#pairL .frame'), lo); $('#pairL .pcap').textContent = `《${lo.title}》`;
      imgInto($('#pairR .frame'), hi); $('#pairR .pcap').textContent = `《${hi.title}》`;
      $('#pairL').dataset.id = lo.slug; $('#pairR').dataset.id = hi.slug;
      $('#reason').textContent = `用一对差异画,测你的「${p.axis}」取向`;
      shownAt = Date.now(); return;
    }
  }
  // 单图自适应(优先从铺满空间的校准集里选)
  const pr = Brain.probe({ seen: [...seen], pool: calib });
  if (!pr) { setTimeout(finish, 300); return; }
  cur = Content.getWork(pr.id);
  $('#single').style.display = '';
  imgInto($('#frame'), cur);
  $('#capT').textContent = `《${cur.title}》`; $('#capB').textContent = `${cur.artist || ''} · ${cur.date || ''}`;
  $('#probeHint').textContent = `正在试探:${pr.axis}`;
  $('#reason').textContent = `这一张在帮我测你的「${pr.axis}」取向`;
  shownAt = Date.now();
}

function tick() {
  count++;
  const conf = Brain.measured();
  $('#progN').textContent = `清晰度 ${pct(conf)} · 已看 ${count}`;
  $('#progBar').style.width = Math.max(conf, count / MAX) * 100 + '%';
  updateViz();
}

function decideSingle(action) {
  const dwell = Date.now() - shownAt;
  if (dwell > 1500) Brain.ingest({ type: 'dwell', workId: cur.slug, value: dwell / 100, context: { ts: Date.now() } });
  Brain.ingest({ type: action, workId: cur.slug, context: { ts: Date.now() } });
  seen.add(cur.slug); tick(); nextStep();
}
function decidePair(side) {
  const chosenId = $(side === 'L' ? '#pairL' : '#pairR').dataset.id;
  const otherId = $(side === 'L' ? '#pairR' : '#pairL').dataset.id;
  Brain.ingest({ type: 'choose', workId: chosenId, context: { ts: Date.now() } });
  Brain.ingest({ type: 'view', workId: otherId, context: { ts: Date.now() } });   // 落选≠不喜欢,只轻记一笔
  seen.add(chosenId); seen.add(otherId); curPair = null; tick(); nextStep();
}

// ── 实时可视化 ─────────────────────────────────────
function updateViz() {
  const m = Brain.meters;
  $('#vEp').textContent = pct(m.epiphany); $('#fEp').style.width = pct(m.epiphany);
  $('#vGr').textContent = pct(m.growth); $('#fGr').style.width = pct(m.growth);
  $('#vCa').textContent = pct(m.calm); $('#fCa').style.width = pct(m.calm);
  // 审美地图:X 明暗 · Y 古今(语料最测得动的两轴)
  const map = $('#map'); map.querySelectorAll('.dot').forEach(d => d.remove());
  seen.forEach(id => { const w = Content.getWork(id); if (!w || !w.color || w.century == null) return; addDot(map, w.color.hsl[2], (w.century - 15) / 6, false); });
  const p = Brain.profile;
  if (p.color && p.era != null) addDot(map, p.color[2], (p.era - 15) / 6, true);
  $('#conf').textContent = '口味清晰度 ' + pct(Brain.measured());
  const top = Brain.topThemes(5), mx = Math.max(1, ...top.map(x => x[1]));
  $('#tbars').innerHTML = top.length ? top.map(([t, v]) => `<div class="tb"><span class="tl">#${esc(t)}</span><span class="tt"><span class="tf" style="width:${Math.round(Math.max(0, v) / mx * 100)}%"></span></span></div>`).join('') : '<div style="font-size:11.5px;color:var(--ink-faint)">还在感受你…</div>';
}
function addDot(map, x, y, you) {
  const d = document.createElement('div'); d.className = 'dot' + (you ? ' you' : '');
  d.style.left = Math.round(Math.max(0, Math.min(1, x)) * 100) + '%';
  d.style.top = Math.round((1 - Math.max(0, Math.min(1, y))) * 100) + '%';
  map.appendChild(d);
}

// ── 报告 ───────────────────────────────────────────
function finish() {
  const r = Brain.report();
  $('#rArche').textContent = r.archetype;
  $('#rBlurb').textContent = r.blurb;
  const axes = r.styleAxes || r.axes;   // KG 风格轴到位优先用,否则用 4 维代理坐标
  const axHead = $('#rAxes').closest('.rb').querySelector('.rh');
  if (axHead) axHead.textContent = r.styleAxes ? '风格轴 · Style Vector(KG)' : '审美坐标 · Aesthetic coordinate';
  $('#rAxes').innerHTML = axes.map(a => `<div class="axis"><div class="al"><span>${a.l}</span><span>${a.r}</span></div><div class="at"><span class="ad" style="left:${Math.round(a.v * 100)}%"></span></div></div>`).join('');
  const sw = [r.color, ...r.loved.slice(0, 4).map(w => w.color ? `hsl(${Math.round(w.color.hsl[0])},${Math.round(w.color.hsl[1] * 70 + 10)}%,${Math.round(w.color.hsl[2] * 100)}%)` : '#ccc')];
  $('#rSw').innerHTML = sw.slice(0, 5).map(c => `<span class="sw" style="background:${c}"></span>`).join('');
  $('#rTags').innerHTML = r.themes.slice(0, 6).map(t => `<span class="tag">${esc(t.t)}</span>`).join('') || '<span style="font-size:12px;color:var(--ink-faint)">—</span>';
  const moodWord = r.mood ? (r.mood.arousal < 0.4 ? '安静沉缓' : r.mood.arousal > 0.6 ? '热烈有动势' : '动静之间') : '—';
  const eraWord = r.era == null ? '—' : (r.era <= 16 ? '文艺复兴前后' : r.era === 17 ? '巴洛克时代' : r.era === 18 ? '18 世纪' : '19 世纪及以后');
  const appetite = r.exploreAppetite > 0.35 ? '高 · 愿意被惊到' : r.exploreAppetite > 0.2 ? '中等' : '低 · 偏爱熟悉';
  const kv = [['情绪基调', moodWord], ['钟爱时代', eraWord], ['惊奇胃口', appetite], ['口味清晰度', pct(r.confidence)], ['评估样本', r.n + ' 次反应']];
  if (r.worldModel) kv.push(['世界模型', r.worldModel]);     // KG 到位才有
  if (r.voice) kv.push(['画外音', r.voice]);
  $('#rKv').innerHTML = kv.map(([k, v]) => `<div class="kv"><span>${k}</span><b>${esc(v)}</b></div>`).join('');
  $('#rMeters').innerHTML = [['顿悟密度', r.meters.epiphany], ['审美成长', r.meters.growth], ['安静感', r.meters.calm]]
    .map(([n, v]) => `<div class="m3"><div class="mv">${pct(v)}</div><div class="mn">${n}</div></div>`).join('');
  $('#rMoments').innerHTML = r.loved.length ? r.loved.map(w => `<div class="mo"><img loading="lazy" src="${w.thumb || w.image}" alt="${esc(w.title)}" title="《${esc(w.title)}》 ${esc(w.artist || '')}"/></div>`).join('') : '<div style="font-size:12px;color:var(--ink-faint)">这次没有特别心动的——也许下次。</div>';
  window._report = r; show('report');
}

// ── 可分享审美卡片(canvas → PNG)──────────────────
function wrapText(ctx, text, maxw) { const out = []; let cur = ''; for (const ch of text) { const t = cur + ch; if (ctx.measureText(t).width > maxw && cur) { out.push(cur); cur = ch; } else cur = t; } if (cur) out.push(cur); return out; }
function rr(c, x, y, w, h, r) { c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath(); }
const swCss = w => w.color ? `hsl(${Math.round(w.color.hsl[0])},${Math.round(w.color.hsl[1] * 70 + 10)}%,${Math.round(w.color.hsl[2] * 100)}%)` : '#ccc';

async function buildCard(r) {
  if (document.fonts) { try { await document.fonts.ready; } catch {} }
  const W = 1080, P = 84, acc = '#b0673a', ink = '#1d1b18', soft = '#4b463e', mute = '#857d6f', line = '#ddd5c6', paper = '#f4f1ea', paper2 = '#ece7db';
  const ws = r.loved.slice(0, 6);
  const imgs = await Promise.all(ws.map(w => new Promise(res => { const im = new Image(); im.onload = () => res(im); im.onerror = () => res(null); im.src = w.thumb || w.image; })));
  const axes = r.styleAxes || r.axes;
  const tmp = document.createElement('canvas').getContext('2d');
  tmp.font = "300 30px 'Noto Sans SC',sans-serif";
  const blurb = wrapText(tmp, r.blurb, W - 2 * P);
  const H = P + 70 + 110 + blurb.length * 44 + 66 + axes.length * 64 + 40 + 94 + 60 + 110 + (imgs.filter(Boolean).length ? (W - 2 * P - 5 * 12) / 6 + 50 : 0) + 110;
  const cv = document.createElement('canvas'); cv.width = W; cv.height = Math.round(H);
  const c = cv.getContext('2d'); c.fillStyle = paper; c.fillRect(0, 0, W, H); c.textBaseline = 'alphabetic';
  let y = P + 24;
  c.textAlign = 'left'; c.fillStyle = ink; c.font = "600 42px 'Noto Serif SC',serif"; c.fillText('aha', P, y); c.fillStyle = acc; c.fillText('.', P + 76, y);
  c.fillStyle = mute; c.font = "500 22px 'JetBrains Mono',monospace"; c.textAlign = 'right'; c.fillText('你的审美 DNA', W - P, y - 6);
  y += 78;
  c.textAlign = 'center'; c.fillStyle = acc; c.font = "600 60px 'Noto Serif SC',serif"; c.fillText(r.archetype, W / 2, y); y += 70;
  c.fillStyle = soft; c.font = "300 30px 'Noto Sans SC',sans-serif"; blurb.forEach(l => { c.fillText(l, W / 2, y); y += 44; }); y += 26;
  c.strokeStyle = line; c.lineWidth = 1; c.beginPath(); c.moveTo(P, y); c.lineTo(W - P, y); c.stroke(); y += 44;
  c.textAlign = 'left';
  axes.forEach(a => { c.fillStyle = mute; c.font = "400 22px 'Noto Sans SC',sans-serif"; c.fillText(a.l, P, y); c.textAlign = 'right'; c.fillText(a.r, W - P, y); c.textAlign = 'left'; const ty = y + 14, tw = W - 2 * P; c.fillStyle = paper2; rr(c, P, ty, tw, 10, 5); c.fill(); c.fillStyle = acc; c.beginPath(); c.arc(P + a.v * tw, ty + 5, 12, 0, 7); c.fill(); y += 64; });
  y += 24;
  const sw = [r.color, ...ws.map(swCss)].slice(0, 5); const swW = (W - 2 * P - 4 * 14) / 5;
  sw.forEach((col, i) => { c.fillStyle = col; rr(c, P + i * (swW + 14), y, swW, 54, 8); c.fill(); }); y += 54 + 44;
  c.fillStyle = soft; c.font = "400 26px 'Noto Sans SC',sans-serif"; c.textAlign = 'center'; c.fillText(r.themes.slice(0, 5).map(t => '#' + t.t).join('    '), W / 2, y); y += 64;
  const M = [['顿悟密度', r.meters.epiphany], ['审美成长', r.meters.growth], ['安静感', r.meters.calm]], mw = (W - 2 * P) / 3;
  M.forEach(([n, v], i) => { const cx = P + mw * i + mw / 2; c.fillStyle = acc; c.font = "600 50px 'JetBrains Mono',monospace"; c.fillText(Math.round(v * 100) + '%', cx, y + 6); c.fillStyle = mute; c.font = "400 22px 'Noto Sans SC',sans-serif"; c.fillText(n, cx, y + 42); }); y += 104;
  const live = imgs.filter(Boolean); if (live.length) { const n = imgs.length, gw = (W - 2 * P - (n - 1) * 12) / n; imgs.forEach((im, i) => { const x = P + i * (gw + 12); c.fillStyle = paper2; rr(c, x, y, gw, gw, 8); c.fill(); if (im) { c.save(); rr(c, x, y, gw, gw, 8); c.clip(); const s = Math.max(gw / im.width, gw / im.height), dw = im.width * s, dh = im.height * s; c.drawImage(im, x + (gw - dw) / 2, y + (gw - dh) / 2, dw, dh); c.restore(); } }); y += gw + 46; }
  c.textAlign = 'center'; c.fillStyle = acc; c.font = "italic 28px 'Source Serif 4',Georgia,serif"; c.fillText('让美,来找你 · art that finds you', W / 2, y); y += 38;
  c.fillStyle = mute; c.font = "400 20px 'JetBrains Mono',monospace"; c.fillText('aha 美学实验室 · ai.zaowuyun.com/aha', W / 2, y);
  return cv;
}
async function saveCard() {
  const r = window._report; if (!r) return; const btn = $('#cardBtn'); btn.textContent = '生成中…';
  try { const cv = await buildCard(r); cv.toBlob(b => { const url = URL.createObjectURL(b); const a = document.createElement('a'); a.href = url; a.download = '我的审美DNA-aha.png'; a.click(); $('#cardImg').src = url; $('#cardPreview').style.display = 'block'; btn.textContent = '⬇ 保存审美卡片'; }, 'image/png'); }
  catch (e) { btn.textContent = '生成失败,重试'; }
}

function startSession() { Brain.reset(); seen = new Set(); count = 0; step = 0; $('#progN').textContent = `清晰度 0% · 已看 0`; $('#progBar').style.width = '0%'; updateViz(); show('device'); nextStep(); }

(async () => {
  await Content.load();
  try { calib = await fetch('data/calib.json').then(r => r.json()); } catch { calib = null; }
  $('#startBtn').onclick = startSession;
  $('#againBtn').onclick = startSession;
  $('#heartBtn').onclick = () => decideSingle('heart');
  $('#skipBtn').onclick = () => decideSingle('skip');
  $('#pairL').onclick = () => decidePair('L');
  $('#pairR').onclick = () => decidePair('R');
  $('#enterBtn').onclick = () => location.href = 'wander.html';
  $('#cardBtn').onclick = saveCard;
  $('#copyBtn').onclick = () => {
    const r = window._report; if (!r) return;
    const txt = `我的审美原型:${r.archetype}\n${r.blurb}\n坐标 ${r.axes.map(a => `${a.l}↔${a.r} ${Math.round(a.v * 100)}%`).join(' · ')}\n钟爱母题 ${r.themes.slice(0, 4).map(t => '#' + t.t).join(' ')}\n顿悟密度${pct(r.meters.epiphany)} · 审美成长${pct(r.meters.growth)} · 安静感${pct(r.meters.calm)}\n—— aha 美学实验室`;
    navigator.clipboard?.writeText(txt).then(() => { $('#copyBtn').textContent = '已复制 ✓'; setTimeout(() => $('#copyBtn').textContent = '复制我的审美摘要', 1800); });
  };
  document.addEventListener('keydown', e => {
    if (!$('#device').classList.contains('on')) return;
    if ($('#single').style.display !== 'none') { if (e.key === 'ArrowRight') decideSingle('heart'); if (e.key === 'ArrowLeft') decideSingle('skip'); }
    else if ($('#pair').style.display !== 'none') { if (e.key === 'ArrowLeft') decidePair('L'); if (e.key === 'ArrowRight') decidePair('R'); }
  });
})();
