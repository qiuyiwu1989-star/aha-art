/* aha · 「艺术史的动力学」板块子导航 ————————————————————————
   用法:页面 <body data-board="dynamics">,末尾加 <script src="js/board-nav.js"></script>(放在 aha-chrome.js 之后)。
   两级导航:顶栏(aha.art logo→站点首页 | 产品日志)在最上;本条板块导航紧随其下、吸顶常驻。
   板块导航 = ‹艺术史的动力学(点=返回板块主页 总图)+ 7 个页面标签(当前页高亮)。
   零依赖、自带 scoped CSS(var(--token,fallback)),幂等;自动收编旧版页内零散导航。 */
(function(){
  if(document.querySelector('.board-navwrap'))return;
  var PAGES=[
    {k:'forces',     h:'kg-forces.html',         t:'总图'},
    {k:'dynamics',   h:'kg-dynamics.html',       t:'关系层'},
    {k:'context',    h:'kg-context.html',        t:'语境层'},
    {k:'contingency',h:'kg-contingency.html',    t:'个体偶发'},
    {k:'timeline',   h:'kg-force-timeline.html', t:'时间线'},
    {k:'tour',       h:'kg-tour-forces.html',    t:'导览'},
    {k:'path',       h:'kg-force-path.html',      t:'连线'}
  ];
  var cur=(document.body.getAttribute('data-board')||'').trim();
  var css=''
   +'.board-navwrap{position:sticky;top:0;z-index:29;background:var(--glass,rgba(244,241,234,.86));'
   +'backdrop-filter:blur(12px) saturate(1.3);-webkit-backdrop-filter:blur(12px) saturate(1.3);'
   +'border-bottom:1px solid var(--line,#ddd5c6)}'
   +'.board-nav{display:flex;align-items:center;gap:4px;flex-wrap:wrap;max-width:1100px;margin:0 auto;'
   +'padding:7px 16px;font-family:var(--mono,"JetBrains Mono",monospace);font-size:12px}'
   +'.board-nav .bn-home{display:inline-flex;align-items:center;gap:4px;font-family:var(--serif,"Noto Serif SC",serif);'
   +'font-weight:600;font-size:14px;color:var(--ink,#1d1b18);text-decoration:none;margin-right:6px;'
   +'padding:3px 9px 3px 6px;border-radius:999px;transition:background .18s,color .18s}'
   +'.board-nav .bn-home:hover{background:var(--paper-2,#ece7db);color:var(--accent,#b0673a)}'
   +'.board-nav .bn-back{font-family:var(--mono);font-size:15px;line-height:1;color:var(--accent,#b0673a);margin-right:2px}'
   +'.board-nav .bn-ver{font-weight:500}'
   +'.board-nav .bn-sep{width:1px;height:15px;background:var(--line,#ddd5c6);margin:0 5px 0 2px}'
   +'.board-nav .bn-board{font-family:var(--serif,"Noto Serif SC",serif);font-size:13px;color:var(--ink-mute,#857d6f);'
   +'text-decoration:none;margin-right:6px}.board-nav .bn-board:hover{color:var(--accent,#b0673a)}'
   +'.board-nav .bn-tabs{display:flex;align-items:center;gap:4px;flex-wrap:wrap;margin-left:auto}'
   +'.board-nav a.bn-t{color:var(--ink-mute,#857d6f);text-decoration:none;padding:4px 11px;border-radius:999px;'
   +'transition:background .18s cubic-bezier(.22,.61,.36,1),color .18s}'
   +'.board-nav a.bn-t:hover{color:var(--accent,#b0673a);background:var(--paper-2,#ece7db)}'
   +'.board-nav a.bn-t.cur{color:#fff;background:var(--ink-soft,#4b463e)}'
   +'@media(max-width:560px){.board-nav{gap:2px;padding:6px 10px;font-size:11px}.board-nav a.bn-t{padding:4px 8px}.board-nav .bn-home{font-size:13px}}'
   /* 收编旧版子页的零散导航:隐藏页内 home-fab / 旧面包屑 / 旧自定义页脚 */
   +'.home-fab{display:none!important}.breadcrumb{display:none!important}body[data-board] footer:not(.site-foot){display:none!important}'
   /* 底部前后导航 */
   +'.board-foot{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px;max-width:1100px;'
   +'margin:46px auto 0;padding:18px 16px;border-top:1px solid var(--line,#ddd5c6);'
   +'font-family:var(--mono,"JetBrains Mono",monospace);font-size:12.5px}'
   +'.board-foot a,.board-foot .bf-home{display:inline-flex;align-items:baseline;gap:7px;text-decoration:none;'
   +'color:var(--ink-mute,#857d6f);padding:8px 15px;border-radius:999px;border:1px solid transparent;'
   +'transition:background .18s,color .18s,border-color .18s}'
   +'.board-foot a:hover{color:var(--accent,#b0673a);background:var(--paper-2,#ece7db)}'
   +'.board-foot .bf-prev{justify-self:start}.board-foot .bf-next{justify-self:end}.board-foot .bf-home{justify-self:center}'
   +'.board-foot a.bf-home{border-color:var(--line,#ddd5c6);color:var(--ink-soft,#4b463e)}'
   +'.board-foot a.bf-home:hover{border-color:var(--accent,#b0673a)}'
   +'.board-foot .bf-home.cur{color:var(--ink-faint,#a9a194);cursor:default}'
   +'.board-foot .bf-t{font-family:var(--serif,"Noto Serif SC",serif);font-weight:600;color:var(--ink,#1d1b18)}'
   +'.board-foot a:hover .bf-t{color:var(--accent,#b0673a)}'
   +'.board-foot .bf-l{color:var(--ink-faint,#a9a194)}'
   +'@media(max-width:560px){.board-foot{gap:5px;padding:14px 8px;font-size:11px}.board-foot a,.board-foot .bf-home{padding:6px 9px;gap:4px}}';
  var st=document.createElement('style');st.textContent=css;document.head.appendChild(st);

  var wrap=document.createElement('div');wrap.className='board-navwrap';
  var back=cur==='forces'?'':'<span class="bn-back">‹</span>';  // 非总图页:板块名前显"返回总图"号
  var html='<nav class="board-nav">'
    +'<a class="bn-home" href="artist-home.html" title="Artist 艺术家 1.0 · 返回品牌首页">Artist <span class="bn-ver">艺术家 1.0</span></a>'
    +'<span class="bn-sep"></span>'
    +'<a class="bn-board" href="kg-forces.html" title="返回本板块首页 · 总图">'+back+'艺术史的动力学</a>'
    +'<span class="bn-tabs">';
  PAGES.forEach(function(p){ html+='<a class="bn-t'+(p.k===cur?' cur':'')+'" href="'+p.h+'">'+p.t+'</a>'; });
  html+='</span></nav>';
  wrap.innerHTML=html;

  var top=document.querySelector('.site-top'); // aha-chrome 顶栏
  if(top&&top.parentNode){ top.parentNode.insertBefore(wrap, top.nextSibling);
    // 吸顶到顶栏正下方:量取顶栏高度作为 sticky 偏移
    var setoff=function(){ var t=document.querySelector('.site-top'); wrap.style.top=(t?t.offsetHeight:0)+'px'; };
    setoff(); window.addEventListener('resize',setoff); setTimeout(setoff,300);
  } else { document.body.insertBefore(wrap, document.body.firstChild); }

  // —— 底部前后导航(线性:上一页 · 回总图 · 下一页)——
  var idx=PAGES.map(function(p){return p.k;}).indexOf(cur);
  if(idx>=0){
    var prev=idx>0?PAGES[idx-1]:null, next=idx<PAGES.length-1?PAGES[idx+1]:null;
    var foot=document.createElement('nav');foot.className='board-foot';
    var cell=function(p,dir){ if(!p)return '<span></span>';
      var l=dir<0?'<span class="bf-l">‹ 上一页</span>':'', r=dir>0?'<span class="bf-l">下一页 ›</span>':'';
      return '<a class="bf-'+(dir<0?'prev':'next')+'" href="'+p.h+'">'+l+'<span class="bf-t">'+p.t+'</span>'+r+'</a>'; };
    var home=cur==='forces'
      ? '<span class="bf-home cur">总图 · 你在这</span>'
      : '<a class="bf-home" href="kg-forces.html">回总图</a>';
    foot.innerHTML=cell(prev,-1)+home+cell(next,1);
    var sf=document.querySelector('.site-foot');
    if(sf&&sf.parentNode){ sf.parentNode.insertBefore(foot, sf); }
    else { document.body.appendChild(foot); }
  }
})();
