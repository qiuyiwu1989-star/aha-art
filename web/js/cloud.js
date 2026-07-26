/* aha · 点云渲染助手 ————————————————————————————————————
   问题:世界观 x/y(及艺术家质心)是真实数据,但被上游量化到粗网格(每轴约 30 档),
   几十幅真画/多位艺术家精确重叠在同一格点 → 画成单点后看着像"稀疏的假网格",
   既骗眼睛(实际很挤)又显得假。
   办法:**确定性微抖动**——按实体 key(作品 file / 艺术家 id)哈希出一个固定的小偏移,
   把同坐标的多个真实点散成一小簇;半透明叠加自然显出密度。
   不改底层数据,只改呈现;偏移确定(同一实体每次一样,不闪、不是随机假点)、有界(默认 ±0.03,
   小于一格步长,点仍落在原坐标的邻域内)。 */
window.AHACloud = (function () {
  function hash(s) { var h = 0; s = String(s || ''); for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return h; }
  // 设计系统数据色(aha-kit.css):赭/绿/蓝/金 + 红/绿²/橙/灰。低唤醒、不用彩虹。
  var DS = ['#b0673a', '#5a7d6f', '#5b7596', '#c98a1a', '#b5483a', '#3a8a5a', '#c2792e', '#857d6f'];
  function ds(i) { i = i | 0; return DS[((i % DS.length) + DS.length) % DS.length]; }   // 按序号取(分类用)
  function dsKey(key) { return ds(hash(key)); }                                          // 按 key 哈希取(稳定)
  function clamp01(v) { return v < 0 ? 0 : v > 1 ? 1 : v; }
  // 估计某一维坐标的"主导格距"(上游量化步长):用高频格点之间的中位间距,
  // 抖动半径取 ≈ 半格 → 相邻格子的散点恰好填满并轻微交叠,网格感消失、读作连续分布。
  function gridStep(vals) {
    vals = (vals || []).filter(function (v) { return typeof v === 'number' && isFinite(v); });
    if (vals.length < 6) return 0.1;
    var cnt = {};
    vals.forEach(function (v) { var k = Math.round(v / 0.005) * 0.005; cnt[k] = (cnt[k] || 0) + 1; });
    var keys = Object.keys(cnt).map(Number).sort(function (a, b) { return a - b; });
    if (keys.length < 2) return 0.1;
    var thr = vals.length / (keys.length * 1.5);              // 密集格点阈值
    var dense = keys.filter(function (k) { return cnt[k] >= thr; });
    var base = dense.length >= 2 ? dense : keys;
    var gaps = [];
    for (var i = 1; i < base.length; i++) { var g = base[i] - base[i - 1]; if (g > 1e-4) gaps.push(g); }
    if (!gaps.length) return 0.1;
    gaps.sort(function (a, b) { return a - b; });
    return gaps[Math.floor(gaps.length / 2)] || 0.1;          // 主导格距(中位)
  }
  // 返回 [dx,dy]:确定性**高斯**抖动(钟形,无硬边 → 相邻格点云平滑融合,不再是方格)。
  // ×31 字符串哈希对连续 key 不雪崩 → 先过整数 finalizer(lowbias32)再取 [0,1) 均匀;σ 默认 0.07≈0.7×主导格距。
  function _mix(h){ h=h|0; h^=h>>>16; h=Math.imul(h,0x7feb352d); h^=h>>>15; h=Math.imul(h,0x846ca68b); h^=h>>>16; return h>>>0; }
  function _u(key){ return (_mix(hash(key)) + 0.5) / 4294967296; }
  function _gauss(u1, u2){ if(u1<1e-9)u1=1e-9; var z=Math.sqrt(-2*Math.log(u1))*Math.cos(6.283185307*u2); return z<-2.8?-2.8:(z>2.8?2.8:z); }
  function jit(key, sX, sY) {
    if (sX == null) sX = 0.07; if (sY == null) sY = sX;
    var zx = _gauss(_u('jx1' + key), _u('jx2' + key));
    var zy = _gauss(_u('jy1' + key), _u('jy2' + key));
    return [zx * sX, zy * sY];
  }
  // 便捷:把 (x,y) 抖动后 clamp 回 [0,1]。可传单一 amp 或 (ampX,ampY) 各轴半径
  function at(key, x, y, ampX, ampY) {
    var d = jit(key, ampX, ampY);
    return [clamp01(x + d[0]), clamp01(y + d[1])];
  }
  return { hash: hash, jit: jit, at: at, gridStep: gridStep, clamp01: clamp01, DS: DS, ds: ds, dsKey: dsKey };
})();
