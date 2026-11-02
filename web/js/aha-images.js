/* Bounded web thumbnails. Local static assets and unknown hosts stay untouched. */
(function(g){
  g.AHAImages = {url:function(src, options){
    if (!src || /^(data:|blob:)/i.test(src)) return src || '';
    options=options||{};
    var u;
    try { u=new URL(src,g.location.href); } catch (_) { return src; }
    if (!((u.origin===g.location.origin && /^\/img\//.test(u.pathname)) || /\.cos\.[a-z0-9-]+\.myqcloud\.com$/i.test(u.hostname))) return src;
    if (u.origin===g.location.origin && /^\/img\/img\//.test(u.pathname)) return src;
    var size=Math.max(64,Math.min(1600,Math.round(Number(options.size)||640)));
    // Verified local derivatives for sources exceeding COS image-processing limits.
    // Match the exact asset path, never retry its giant original.
    var sourcePath;
    try { sourcePath=decodeURIComponent(u.pathname).replace(/^\/img\//,'/'); } catch (_) { sourcePath=u.pathname; }
    var derivative={'/artworks/油画数据集/yh/upload/workImage_ori/20160901/20160901112148rxyIzJmh.jpg':'34754','/artworks/油画数据集/yh/upload1/workImage_ori/20160913/20160913163826iB1gJwUh.jpg':'184913'}[sourcePath];
    if(derivative){
      return new URL('/assets/derivatives/'+derivative+'-'+(size<=720?'720':'1600')+'.webp',g.location.origin).href;
    }
    var format=options.format==='jpeg'?'jpg':'webp';
    // Preserve unrelated signed/query parameters; replace existing COS transforms.
    var parts=u.search.slice(1).split('&').filter(function(p){return p && !/^(imageMogr2|imageView2)(\/|=|$)/.test(p);});
    parts.push('imageMogr2/thumbnail/'+size+'x'+size+'/format/'+format);
    u.search='?'+parts.join('&');
    return u.href;
  }};
})(window);
