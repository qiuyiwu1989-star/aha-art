/* aha 通用图像容错(全站唯一机制)——任何 <img> 加载失败都优雅降级,绝不出现浏览器的裂图图标。
   策略:图片请求失败直接换成暖色"图片暂缺"占位，避免重试大尺寸原图。
   capture 阶段挂在 document 上,动态插入的 <img> 同样兜底。尽量早加载(放 <head> 首个脚本)。 */
(function () {
  if (window.__ahaImgGuard) return;
  window.__ahaImgGuard = true;

  // 暖墙色 + 画框轮廓的占位图(SVG data-URI,不会再触发网络/错误)
  var PLACEHOLDER = 'data:image/svg+xml;charset=utf8,' + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" viewBox="0 0 600 600">' +
    '<rect width="600" height="600" fill="#e7e2d6"/>' +
    '<g fill="none" stroke="#c4b99f" stroke-width="3">' +
    '<rect x="64" y="64" width="472" height="472" rx="8"/>' +
    '<circle cx="220" cy="210" r="40"/>' +
    '<path d="M64 470 L230 300 L340 410 L430 320 L536 430"/></g>' +
    '<text x="300" y="556" text-anchor="middle" font-family="monospace" font-size="22" fill="#a99d83">图片暂缺</text>' +
    '</svg>');

  var retryState=new WeakMap();
  function handle(im) {
    if (!im || im.tagName !== 'IMG') return;
    var st = im.getAttribute('data-imgguard');
    var src = im.getAttribute('src') || '';
    if (src === PLACEHOLDER) return; // A later src assignment may fail again; only the placeholder is terminal.

    // Retry only known bounded thumbnails, once per element/source. Never expand to originals.
    if (/imageMogr2\/thumbnail\/|\/assets\/derivatives\//.test(src)) {
      var previous=retryState.get(im);
      if (!previous || previous.src!==src) {
        var state={src:src,pending:true};retryState.set(im,state);
        im.removeAttribute('srcset');im.removeAttribute('sizes');
        setTimeout(function(){
          state.pending=false;
          if(im.isConnected!==false && im.getAttribute('src')===src)im.src=src;
        },800);
        return;
      }
      if(previous.pending)return;
    }
    // 缩略图失败直接占位，不请求可能几十MB的原图。
    im.removeAttribute('srcset');
    im.removeAttribute('sizes');
    im.alt = im.alt || '图片暂时无法加载';
    im.title = '图片暂时无法加载，稍后刷新可重试';
    // 任意坏源 → 占位封口
    im.setAttribute('data-imgguard', 'done');
    if (src !== PLACEHOLDER) im.src = PLACEHOLDER;
    im.style.objectFit = im.style.objectFit || 'cover';
  }

  // error 事件不冒泡,必须用 capture 才能在 document 层捕获(含动态插入的 <img>)
  document.addEventListener('error', function (e) { handle(e.target); }, true);

  // 兜底:对页面加载时已经失败、错过事件的图,DOM 就绪后扫一遍 complete && naturalWidth===0
  function sweep() {
    var imgs = document.getElementsByTagName('img');
    for (var i = 0; i < imgs.length; i++) {
      var im = imgs[i];
      if (im.complete && im.naturalWidth === 0 && im.getAttribute('src') && im.getAttribute('data-imgguard') !== 'done') handle(im);
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', sweep);
  else sweep();
  window.addEventListener('load', sweep);
})();
