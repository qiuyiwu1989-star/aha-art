/* aha · 点云舞台 (canvas) ————————————————————————————————————
   把 2 万~15 万个真实作品点画成可缩放/平移/聚光/筛选的全屏点云。
   SVG 在这个量级会卡(每点一个 DOM 节点 + 事件),改用 canvas 2D:
   · 离屏 base 画布:相机/筛选/配色变化时才整张重画(按颜色分桶,fill 次数=颜色数)。
   · 主画布:悬停时只 drawImage(base) + 一层纸色光幕 + 把命中点重画亮 → 60fps 与点数无关。
   · 命中检测用空间哈希网格(O(1) 邻域查询),不遍历全部点。
   依赖 AHACloud(确定性 jitter + 设计系统数据色)。 */
window.AHAStage = function (opts) {
  var cv = opts.canvas, pts = opts.points || [];
  var px = opts.px || function (p) { return +p.x; };
  var py = opts.py || function (p) { return +p.y; };
  var keyOf = opts.key || function (p) { return p.id || p.title || ''; };
  var colorOf = opts.colorOf || function () { return '#b0673a'; };
  var groupOf = opts.groupOf || null;          // 返回点所属分组 id(图例筛选用),无则不筛
  var labels = opts.labels || [];              // [{x,y,text,color}] 数据坐标
  var C = Object.assign({ axis: '#ddd5c6', halo: '#f6f1e7', ring: '#b0673a', label: '#a89f8f', dim: '#bcb3a2', chip: 'rgba(246,241,231,.82)', chipLine: 'rgba(221,213,198,.7)' }, opts.colors || {});
  var DOT_A = opts.alpha || 0.78;              // 点不透明度:暗底上大地色高对比
  var onHover = opts.onHover || function () { }, onLeave = opts.onLeave || function () { }, onPick = opts.onPick || function () { };

  var dpr = Math.max(1, Math.min(2.5, window.devicePixelRatio || 1));
  var ctx = cv.getContext('2d');
  var base = document.createElement('canvas'), bx = base.getContext('2d');
  var S = 0, PW = 0, m = 0;                     // S=css 边长, PW=设备像素, m=内边距
  var DX = new Float32Array(pts.length), DY = new Float32Array(pts.length); // jitter 后数据坐标[0,1]
  var WX = new Float32Array(pts.length), WY = new Float32Array(pts.length); // zoom=1 时的像素坐标
  var COL = new Array(pts.length), GRP = new Array(pts.length);
  var buckets = {};                            // 颜色 -> [索引]
  var view = { z: 1, ox: 0, oy: 0 };           // screen = world*z + (ox,oy)
  var FILTER = null;                           // null=全显;否则 Set(分组 id)
  var hov = -1;
  var grid = null, cell = 14, gw = 0, gh = 0;

  // —— jitter 预计算(一次)——
  (function () {
    var xs = [], ys = [];
    for (var i = 0; i < pts.length; i++) { xs.push(px(pts[i])); ys.push(py(pts[i])); }
    var ax = 0.05, ay = 0.05;
    if (window.AHACloud) { ax = AHACloud.gridStep(xs) * 0.7; ay = AHACloud.gridStep(ys) * 0.7; }
    for (var j = 0; j < pts.length; j++) {
      var x = px(pts[j]), y = py(pts[j]);
      if (window.AHACloud) { var d = AHACloud.at(keyOf(pts[j]), x, y, ax, ay); DX[j] = d[0]; DY[j] = d[1]; }
      else { DX[j] = x < 0 ? 0 : x > 1 ? 1 : x; DY[j] = y < 0 ? 0 : y > 1 ? 1 : y; }
      GRP[j] = groupOf ? groupOf(pts[j]) : null;
    }
  })();

  function rad() { return Math.min(4.3, 1.75 * Math.pow(view.z, 0.30)); }

  function layout() {
    S = cv.clientWidth; if (!S) S = cv.parentNode.clientWidth;
    var hpx = cv.clientHeight || S; if (hpx < S) S = hpx;   // 取正方形(等比,不扭曲度量)
    PW = Math.round(S * dpr);
    cv.width = PW; cv.height = PW; base.width = PW; base.height = PW;
    m = S * 0.055;
    for (var i = 0; i < pts.length; i++) { WX[i] = m + DX[i] * (S - 2 * m); WY[i] = m + (1 - DY[i]) * (S - 2 * m); }
    buildGrid();
  }

  function buildGrid() {
    gw = Math.ceil(S / cell) + 1; gh = gw; grid = new Array(gw * gh);
    for (var i = 0; i < pts.length; i++) {
      var gx = WX[i] / cell | 0, gy = WY[i] / cell | 0, k = gy * gw + gx;
      (grid[k] || (grid[k] = [])).push(i);
    }
  }

  function rebuildColors() {
    buckets = {};
    for (var i = 0; i < pts.length; i++) { var c = COL[i] = colorOf(pts[i]); (buckets[c] || (buckets[c] = [])).push(i); }
  }
  rebuildColors();

  function sx(i) { return WX[i] * view.z + view.ox; }
  function sy(i) { return WY[i] * view.z + view.oy; }

  function renderBase() {
    bx.setTransform(dpr, 0, 0, dpr, 0, 0); bx.clearRect(0, 0, S, S);
    // 轴十字
    var cx = (S / 2) * view.z + view.ox, cy = (S / 2) * view.z + view.oy;
    bx.strokeStyle = C.axis; bx.lineWidth = 1;
    bx.beginPath(); bx.moveTo(cx, 0); bx.lineTo(cx, S); bx.moveTo(0, cy); bx.lineTo(S, cy); bx.stroke();
    var r = rad(), active = FILTER;
    // 被筛掉的点:统一淡隐(画在底层)
    if (active) {
      bx.fillStyle = C.dim; bx.globalAlpha = 0.07; bx.beginPath();
      for (var i = 0; i < pts.length; i++) {
        if (active.has(GRP[i])) continue; var X = sx(i), Y = sy(i); if (X < -6 || X > S + 6 || Y < -6 || Y > S + 6) continue;
        bx.moveTo(X + r, Y); bx.arc(X, Y, r, 0, 6.2832);
      } bx.fill();
    }
    // 在显点:按颜色分桶,每桶一次 fill
    bx.globalAlpha = DOT_A;
    for (var c in buckets) {
      var arr = buckets[c]; bx.fillStyle = c; bx.beginPath(); var drew = false;
      for (var a = 0; a < arr.length; a++) {
        var j = arr[a]; if (active && !active.has(GRP[j])) continue;
        var X2 = sx(j), Y2 = sy(j); if (X2 < -6 || X2 > S + 6 || Y2 < -6 || Y2 > S + 6) continue;
        bx.moveTo(X2 + r, Y2); bx.arc(X2, Y2, r, 0, 6.2832); drew = true;
      } if (drew) bx.fill();
    }
    bx.globalAlpha = 1;
    // 标签层:KG 权威坐标 + 去重叠排布(弹簧回锚 + 互斥分离)+ 领域多边形 + 白描边粗体,浮在最上层
    bx.font = '600 14px "Noto Serif SC",serif'; bx.textAlign = 'center'; bx.textBaseline = 'middle'; bx.lineJoin = 'round';
    var LB = [];
    for (var L = 0; L < labels.length; L++) {
      var lb = labels[L];
      var ax = (m + lb.x * (S - 2 * m)) * view.z + view.ox, ay = (m + (1 - lb.y) * (S - 2 * m)) * view.z + view.oy;
      LB.push({ lb: lb, ax: ax, ay: ay, lx: ax, ly: ay, w: bx.measureText(lb.text).width + 12, h: 21 });
    }
    for (var it = 0; it < 40; it++) {                       // 去重叠
      for (var i = 0; i < LB.length; i++) { LB[i].lx += (LB[i].ax - LB[i].lx) * 0.08; LB[i].ly += (LB[i].ay - LB[i].ly) * 0.08; }
      for (var i2 = 0; i2 < LB.length; i2++) for (var j = i2 + 1; j < LB.length; j++) {
        var A = LB[i2], B = LB[j], dx = B.lx - A.lx, dy = B.ly - A.ly;
        var ox = (A.w + B.w) / 2 - Math.abs(dx), oy = (A.h + B.h) / 2 + 5 - Math.abs(dy);
        if (ox > 0 && oy > 0) { if (ox < oy) { var s = (dx < 0 ? -1 : 1) * ox / 2 || 0.5; A.lx -= s; B.lx += s; } else { var s2 = (dy < 0 ? -1 : 1) * oy / 2 || 0.5; A.ly -= s2; B.ly += s2; } }
      }
    }
    for (var p = 0; p < LB.length; p++) {                   // 领域多边形(有 poly 的:worldview 区)
      var L2 = LB[p].lb; if (!(L2.poly && L2.poly.length >= 3)) continue;
      var V = [], vx2 = 0, vy2 = 0;
      for (var k = 0; k < L2.poly.length; k++) { var px2 = (m + L2.poly[k][0] * (S - 2 * m)) * view.z + view.ox, py2 = (m + (1 - L2.poly[k][1]) * (S - 2 * m)) * view.z + view.oy; V.push([px2, py2]); vx2 += px2; vy2 += py2; }
      vx2 /= V.length; vy2 /= V.length; bx.beginPath();
      for (var k2 = 0; k2 < V.length; k2++) { var ddx = V[k2][0] - vx2, ddy = V[k2][1] - vy2, dd = Math.hypot(ddx, ddy) || 1, ex = V[k2][0] + ddx / dd * 14, ey = V[k2][1] + ddy / dd * 14; if (k2 === 0) bx.moveTo(ex, ey); else bx.lineTo(ex, ey); }
      bx.closePath();
      var lc0 = L2.color || C.label;
      bx.globalAlpha = 0.06; bx.fillStyle = lc0; bx.fill();
      bx.globalAlpha = 0.5; bx.strokeStyle = lc0; bx.lineWidth = 1.5; bx.setLineDash([6, 5]); bx.stroke(); bx.setLineDash([]);
    }
    for (var q = 0; q < LB.length; q++) {                   // 连接线 + 锚点 + 标签
      var T = LB[q], lc = T.lb.color || C.label;
      if (Math.hypot(T.lx - T.ax, T.ly - T.ay) > 16) { bx.globalAlpha = 0.5; bx.strokeStyle = lc; bx.lineWidth = 1; bx.setLineDash([2, 2]); bx.beginPath(); bx.moveTo(T.ax, T.ay); bx.lineTo(T.lx, T.ly); bx.stroke(); bx.setLineDash([]); }
      if (!T.lb.poly) { bx.globalAlpha = 1; bx.fillStyle = lc; bx.beginPath(); bx.arc(T.ax, T.ay, 3.4, 0, 6.2832); bx.fill(); bx.strokeStyle = C.halo; bx.lineWidth = 1.5; bx.stroke(); }
      bx.globalAlpha = 1; bx.lineWidth = 3.5; bx.strokeStyle = C.halo; bx.strokeText(T.lb.text, T.lx, T.ly);
      bx.fillStyle = lc; bx.fillText(T.lb.text, T.lx, T.ly);
    }
    bx.globalAlpha = 1;
  }

  function paint() {
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, PW, PW); ctx.drawImage(base, 0, 0);
    if (hov >= 0) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.globalAlpha = 1;
      var X = sx(hov), Y = sy(hov), r = Math.max(5, rad() * 2.1);
      ctx.fillStyle = C.halo; ctx.beginPath(); ctx.arc(X, Y, r + 5, 0, 6.2832); ctx.fill();   // 局部纸色光晕:只托起命中点,不动其余
      ctx.fillStyle = COL[hov]; ctx.beginPath(); ctx.arc(X, Y, r, 0, 6.2832); ctx.fill();
      ctx.strokeStyle = C.ring; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(X, Y, r + 3, 0, 6.2832); ctx.stroke();
    }
  }

  // —— 帧调度 ——
  var needB = false, needP = false, raf = 0;
  function tick() { raf = 0; if (needB) { renderBase(); needB = false; needP = true; } if (needP) { paint(); needP = false; } }
  function schedule() { if (!raf) raf = requestAnimationFrame(tick); }
  function dirtyBase() { needB = true; schedule(); }
  function dirtyPaint() { needP = true; schedule(); }

  // —— 命中检测 ——
  function hit(cssx, cssy) {
    var wx = (cssx - view.ox) / view.z, wy = (cssy - view.oy) / view.z;
    var gx = wx / cell | 0, gy = wy / cell | 0, best = -1, bd = (12 / view.z); bd *= bd;
    for (var oy = -1; oy <= 1; oy++) for (var ox = -1; ox <= 1; ox++) {
      var k = (gy + oy) * gw + (gx + ox), arr = grid[k]; if (!arr) continue;
      for (var a = 0; a < arr.length; a++) {
        var i = arr[a]; if (FILTER && !FILTER.has(GRP[i])) continue;
        var ddx = WX[i] - wx, ddy = WY[i] - wy, d = ddx * ddx + ddy * ddy;
        if (d < bd) { bd = d; best = i; }
      }
    } return best;
  }

  // —— 相机 ——
  function clampPan() {                                // 让正方形始终铺满视口,拖不出去
    var min = Math.min(0, S - S * view.z);
    if (view.ox > 0) view.ox = 0; if (view.ox < min) view.ox = min;
    if (view.oy > 0) view.oy = 0; if (view.oy < min) view.oy = min;
  }
  function zoomAt(cssx, cssy, factor) {
    var nz = Math.max(1, Math.min(14, view.z * factor)); if (nz === view.z) return;
    var wx = (cssx - view.ox) / view.z, wy = (cssy - view.oy) / view.z;
    view.z = nz; view.ox = cssx - wx * nz; view.oy = cssy - wy * nz; clampPan(); dirtyBase();
  }

  // —— 事件 ——
  var ptrs = {}, dragId = -1, lastX = 0, lastY = 0, moved = 0, pinchD = 0;
  function rel(e) { var b = cv.getBoundingClientRect(); return [e.clientX - b.left, e.clientY - b.top]; }
  cv.addEventListener('pointerdown', function (e) {
    cv.setPointerCapture(e.pointerId); ptrs[e.pointerId] = rel(e);
    if (Object.keys(ptrs).length === 1) { dragId = e.pointerId; var r = ptrs[e.pointerId]; lastX = r[0]; lastY = r[1]; moved = 0; }
    else if (Object.keys(ptrs).length === 2) { var ks = Object.keys(ptrs); var a = ptrs[ks[0]], b2 = ptrs[ks[1]]; pinchD = Math.hypot(a[0] - b2[0], a[1] - b2[1]); }
  });
  cv.addEventListener('pointermove', function (e) {
    var r = rel(e);
    if (ptrs[e.pointerId]) ptrs[e.pointerId] = r;
    var n = Object.keys(ptrs).length;
    if (n >= 2) {                                       // 双指捏合
      var ks = Object.keys(ptrs), a = ptrs[ks[0]], b2 = ptrs[ks[1]], d = Math.hypot(a[0] - b2[0], a[1] - b2[1]);
      if (pinchD) zoomAt((a[0] + b2[0]) / 2, (a[1] + b2[1]) / 2, d / pinchD); pinchD = d;
      if (hov >= 0) { hov = -1; onLeave(); dirtyPaint(); } return;
    }
    if (dragId === e.pointerId && (e.buttons & 1 || e.pointerType !== 'mouse')) {  // 拖拽平移
      var dx = r[0] - lastX, dy = r[1] - lastY; moved += Math.abs(dx) + Math.abs(dy);
      view.ox += dx; view.oy += dy; lastX = r[0]; lastY = r[1]; clampPan();
      if (hov >= 0) { hov = -1; onLeave(); } dirtyBase(); return;
    }
    // 悬停命中
    var h = hit(r[0], r[1]);
    if (h !== hov) { hov = h; if (h >= 0) { onHover(pts[h], e.clientX, e.clientY); } else onLeave(); dirtyPaint(); }
    else if (h >= 0) onHover(pts[h], e.clientX, e.clientY);   // 移动时跟随定位 tip
  });
  function up(e) {
    var was = dragId === e.pointerId; delete ptrs[e.pointerId]; pinchD = 0;
    if (was) { dragId = -1; if (moved < 5) { var r = rel(e); var h = hit(r[0], r[1]); if (h >= 0) onPick(pts[h]); } }
    if (Object.keys(ptrs).length === 1) { var k = Object.keys(ptrs)[0]; dragId = +k; lastX = ptrs[k][0]; lastY = ptrs[k][1]; }
  }
  cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
  cv.addEventListener('pointerleave', function () { if (hov >= 0 && dragId < 0) { hov = -1; onLeave(); dirtyPaint(); } });
  cv.addEventListener('wheel', function (e) { e.preventDefault(); var r = rel(e); zoomAt(r[0], r[1], e.deltaY < 0 ? 1.18 : 1 / 1.18); }, { passive: false });
  cv.addEventListener('dblclick', function () { view.z = 1; view.ox = 0; view.oy = 0; dirtyBase(); });

  // —— 对外 ——
  function vcount() { if (!FILTER) return pts.length; var n = 0; for (var i = 0; i < pts.length; i++) if (FILTER.has(GRP[i])) n++; return n; }
  layout(); renderBase(); paint();
  var ro = window.ResizeObserver ? new ResizeObserver(function () { layout(); dirtyBase(); }) : null;
  if (ro) ro.observe(cv);

  return {
    setColor: function (fn) { colorOf = fn; rebuildColors(); dirtyBase(); },
    setGroup: function (fn) { groupOf = fn; for (var i = 0; i < pts.length; i++) GRP[i] = fn(pts[i]); dirtyBase(); },
    setFilter: function (set) { FILTER = (set && set.size) ? set : null; dirtyBase(); return vcount(); },
    reset: function () { view.z = 1; view.ox = 0; view.oy = 0; dirtyBase(); },
    zoomIn: function () { zoomAt(S / 2, S / 2, 1.4); }, zoomOut: function () { zoomAt(S / 2, S / 2, 1 / 1.4); },
    visibleCount: vcount, relayout: function () { layout(); dirtyBase(); },
    destroy: function () { if (ro) ro.disconnect(); }
  };
};
