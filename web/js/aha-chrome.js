/* aha-chrome.js · 统一站点骨架(顶栏 + 底栏),自带样式、零依赖
   用法:任意页 <body> 末尾加一行即可,不必引 aha-kit.css:
     <script src="js/aha-chrome.js"></script>
   行为:DOM 就绪后注入一段 scoped CSS(用 var(--token,兜底)兼容有/无 aha-kit 的页)
        + 顶栏(brand aha.art → 主页/博物馆;右侧"产品日志"→ log.html)+ 底栏(备案 + 出品)。
   - 幂等:已存在 .site-top / .site-foot / 本样式则跳过。
   - <body data-no-top>:不要顶栏(主页/有大 hero 的日志页);底栏照常。
   - <body data-home="xxx.html">:改顶栏 brand 指向(默认 museum.html=主页)。 */
(function(){
  var HOME='museum.html', LOG='log.html', BEIAN='浙ICP备2021038972号-8', PRODUCER='浙江大学国际设计研究院';
  var IDI_URL='https://idi.zju.edu.cn/', LIB_URL='https://libweb.zju.edu.cn/', ZWY_URL='https://www.zaowuyun.com/';
  var CSS=''+
  '.site-top{display:flex;align-items:center;justify-content:space-between;gap:16px;'+
    'padding:max(11px,env(safe-area-inset-top)) max(20px,env(safe-area-inset-right)) 11px max(20px,env(safe-area-inset-left));'+
    'background:var(--glass,rgba(244,241,234,.58));'+
    'border-bottom:1px solid var(--glass-line,rgba(221,213,198,.55));'+
    'position:sticky;top:0;z-index:40;backdrop-filter:blur(16px) saturate(1.4);'+
    '-webkit-backdrop-filter:blur(16px) saturate(1.4)}'+
  '.site-top .brand{font-family:var(--serif,"Noto Serif SC",serif);font-size:20px;font-weight:600;'+
    'letter-spacing:-.01em;color:var(--ink,#1d1b18);text-decoration:none}'+
  '.site-top .brand .dot{color:var(--accent,#b0673a)}'+
  '.site-top .st-link{font-family:var(--mono,"JetBrains Mono",monospace);font-size:11px;'+
    'letter-spacing:.04em;color:var(--ink-mute,#857d6f);text-decoration:none;transition:color .18s}'+
  '.site-top .st-link:hover{color:var(--accent,#b0673a)}'+
  '.site-foot{margin-top:48px;padding:22px 20px 24px;border-top:1px solid var(--line,#ddd5c6);'+
    'text-align:center;font-family:var(--mono,"JetBrains Mono",monospace);font-size:11px;'+
    'color:var(--ink-faint,#a89f8f);line-height:1.9;letter-spacing:.03em}'+
  '.site-foot .sf-nav{margin-bottom:10px}'+
  '.site-foot .sf-nav a{color:var(--ink-mute,#857d6f);text-decoration:none;font-size:11.5px;'+
    'transition:color .18s}'+
  '.site-foot .sf-nav a:hover{color:var(--accent,#b0673a)}'+
  '.site-foot .sf-row{margin:1px 0}'+
  '.site-foot .sf-sep{margin:0 10px;color:var(--ink-faint,#a89f8f);opacity:.5}'+
  '.site-foot a{color:var(--ink-mute,#857d6f);text-decoration:none}'+
  '.site-foot a:hover{color:var(--accent,#b0673a)}';
  function node(html){var t=document.createElement('template');t.innerHTML=html.trim();return t.content.firstChild;}
  function mount(){
    var body=document.body, home=body.getAttribute('data-home')||HOME;
    if(!document.getElementById('aha-chrome-style')){
      var st=document.createElement('style');st.id='aha-chrome-style';st.textContent=CSS;
      document.head.appendChild(st);
    }
    if(!body.hasAttribute('data-no-top') && !document.querySelector('.site-top')){
      body.insertBefore(node(
        '<header class="site-top">'+
          '<a class="brand" href="'+home+'">aha<span class="dot">.</span>art</a>'+
          '<a class="st-link" href="'+LOG+'">产品日志 · log</a>'+
        '</header>'), body.firstChild);
    }
    if(!document.querySelector('.site-foot')){
      body.appendChild(node(
        '<footer class="site-foot">'+
          '<nav class="sf-nav">'+
            '<a href="'+LOG+'">全部体验</a><span class="sf-sep">·</span>'+
            '<a href="compass.html">体验地图</a><span class="sf-sep">·</span>'+
            '<a href="dashboard.html">管理后台</a><span class="sf-sep">·</span>'+
            '<a href="design-system.html">设计系统</a><span class="sf-sep">·</span>'+
            '<a href="sitemap.html">网站地图</a>'+
          '</nav>'+
          '<div class="sf-row">出品 · <a href="'+IDI_URL+'" target="_blank" rel="noopener">'+PRODUCER+'</a>'+
          '<span class="sf-sep">·</span>数据支持 · <a href="'+LIB_URL+'" target="_blank" rel="noopener">浙江大学图书馆</a></div>'+
          '<div class="sf-row">技术支持 · <a href="'+ZWY_URL+'" target="_blank" rel="noopener">造物云</a>'+
          '<span class="sf-sep">·</span>备案 · <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener">'+BEIAN+'</a></div>'+
        '</footer>'));
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);
  else mount();
})();
