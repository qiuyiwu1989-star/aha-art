// 微交互内核:① 从缩略图取主色,染整个空间(情绪化背景)
//             ② 画面随光标微倾,静止时缓慢呼吸(动则活、静则平)
// 全程尊重 prefers-reduced-motion。
const REDUCE = matchMedia('(prefers-reduced-motion: reduce)').matches;

// 从 lqip(极小 data-URI)取平均色 → [r,g,b]
const _cache = {};
export function ambientColor(work) {
  return new Promise(res => {
    if (_cache[work.slug]) return res(_cache[work.slug]);
    const img = new Image();
    img.onload = () => {
      try {
        const c = document.createElement('canvas'); c.width = c.height = 8;
        const x = c.getContext('2d'); x.drawImage(img, 0, 0, 8, 8);
        const d = x.getImageData(0, 0, 8, 8).data;
        let r = 0, g = 0, b = 0, n = 0;
        for (let i = 0; i < d.length; i += 4) { r += d[i]; g += d[i + 1]; b += d[i + 2]; n++; }
        const c3 = [Math.round(r / n), Math.round(g / n), Math.round(b / n)];
        _cache[work.slug] = c3; res(c3);
      } catch { res([34, 32, 24]); }
    };
    img.onerror = () => res([34, 32, 24]);
    img.src = work.lqip || '';
  });
}

export function initAmbient(stageEl, canvasEl) {
  let bg = stageEl.querySelector('.moodbg');
  if (!bg) { bg = document.createElement('div'); bg.className = 'moodbg'; stageEl.prepend(bg); }

  // 微视差 + 呼吸(reduce 模式跳过)
  if (!REDUCE && canvasEl) {
    let tx = 0, ty = 0, cx = 0, cy = 0, raf = null;
    const loop = () => {
      cx += (tx - cx) * 0.08; cy += (ty - cy) * 0.08;
      const af = canvasEl.querySelector('.artframe');
      if (af) af.style.transform = `perspective(1300px) rotateY(${cx * 3}deg) rotateX(${-cy * 3}deg)`;
      raf = (Math.abs(tx - cx) > .001 || Math.abs(ty - cy) > .001) ? requestAnimationFrame(loop) : null;
    };
    canvasEl.addEventListener('pointermove', (e) => {
      const r = canvasEl.getBoundingClientRect();
      tx = (e.clientX - r.left) / r.width - .5;
      ty = (e.clientY - r.top) / r.height - .5;
      if (!raf) raf = requestAnimationFrame(loop);
    });
    canvasEl.addEventListener('pointerleave', () => { tx = 0; ty = 0; if (!raf) raf = requestAnimationFrame(loop); });
  }

  return {
    setMood(work) {
      ambientColor(work).then(([r, g, b]) => {
        // 染成深色环境(画作浮在其上),平滑过渡靠 CSS transition
        bg.style.backgroundColor = `rgb(${(r * .30) | 0},${(g * .30) | 0},${(b * .32) | 0})`;
        stageEl.style.setProperty('--mood', `rgb(${r},${g},${b})`);
      });
    },
    breathe(on) {
      const af = canvasEl && canvasEl.querySelector('.artframe');
      if (af && !REDUCE) af.classList.toggle('breath', !!on);
    }
  };
}
