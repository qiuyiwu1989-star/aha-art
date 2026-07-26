/* aha · 「艺术史的动力学」板块 · 真迹证据 ————————————————————————
   把"力"摆成实物:任意元素加 data-works="ARTIST.xxx"(可选 data-cn / data-lab / data-max),
   挂本脚本后调用 BoardWorks.ready.then(()=>BoardWorks.hydrate(根)) 即自动填入该艺术家真迹缩略图。
   数据 data/kg_artist_images.json;无图者优雅留白(移除占位)。零依赖、自带 scoped CSS。 */
window.BoardWorks=(function(){
  var cache={};
  var ready=fetch('data/kg_artist_images.json').then(function(r){return r.json();})
    .then(function(d){cache=d||{};return cache;}).catch(function(){return cache;});
  var css=''
   +'.bw-cap{font-family:var(--mono,monospace);font-size:10px;letter-spacing:.06em;color:var(--accent,#b0673a);margin:9px 0 6px}'
   +'.bw-lab{font-size:11px;color:var(--ink-mute,#857d6f);margin-bottom:4px;font-family:var(--sans,sans-serif)}'
   +'.bw-row{display:flex;gap:6px;flex-wrap:wrap}'
   +'.bw-row a{line-height:0;display:inline-block}'
   +'.bw-row img{width:62px;height:62px;object-fit:cover;border-radius:6px;border:1px solid var(--line,#ddd5c6);'
   +'background:var(--paper-2,#ece7db);transition:transform .18s cubic-bezier(.22,.61,.36,1)}'
   +'.bw-row a:hover img{transform:scale(1.05)}';
  var st=document.createElement('style');st.textContent=css;document.head.appendChild(st);

  function thumbs(id,cn,max){
    if(!id||id.indexOf('ARTIST.')!==0)return '';
    var it=((cache[id]||{}).items)||[];if(!it.length)return '';
    return '<div class="bw-row">'+it.slice(0,max||3).map(function(w){
      return '<a href="kg-artist.html?id='+id+'" title="'+String(w.title||'').replace(/"/g,'')+' '+(w.date||'')
        +'"><img loading="lazy" src="'+w.file+'" alt="'+(cn||'')+'"></a>';
    }).join('')+'</div>';
  }
  function hydrate(root){
    (root||document).querySelectorAll('[data-works]').forEach(function(el){
      var t=thumbs(el.getAttribute('data-works'),el.getAttribute('data-cn'),+(el.getAttribute('data-max')||3));
      if(t){var lab=el.getAttribute('data-lab');
        el.innerHTML=(lab?'<div class="bw-lab">'+lab+'</div>':'')+t;el.removeAttribute('data-works');}
      else el.remove();  // 无图:优雅留白
    });
  }
  function has(id){return !!(((cache[id]||{}).items)||[]).length;}
  return {ready:ready,thumbs:thumbs,hydrate:hydrate,has:has};
})();
