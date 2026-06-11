/* aha · 图标系统 ——————————————————————————————————————————————
   线性(stroke)图标,1.7px 描边,圆角端点 —— 契合"低唤醒 · 安静的纸"调性。
   图标取自 Lucide(https://lucide.dev, ISC/MIT),按 aha 需要裁剪。2026-06 扩充导航/通用图标(home/search/create/me/graph/works…)。
   用法:  el.innerHTML = AHAIcons.svg('mode')        // 返回 <svg>…</svg>
          AHAIcons.svg('heart',{fill:true})          // 实心(收藏选中)
   设计系统:这是全站唯一图标来源,新增图标只加到这里;design-system.html 有展板。
   —— 禁止再用 emoji 当功能图标。 */
window.AHAIcons = (function(){
  var P = {
    mode:    '<rect x="3" y="3" width="7" height="7" rx="1.3"/><rect x="14" y="3" width="7" height="7" rx="1.3"/><rect x="3" y="14" width="7" height="7" rx="1.3"/><rect x="14" y="14" width="7" height="7" rx="1.3"/>', // 切换阅读方式(田字格)
    museum:  '<path d="M3 21h18"/><path d="M5 21V10"/><path d="M9 21V10"/><path d="M15 21V10"/><path d="M19 21V10"/><path d="M12 3 21 8H3Z"/>',                                     // 美术馆(山花殿堂)
    frame:   '<rect x="3" y="3" width="18" height="18" rx="1.5"/><rect x="7" y="7" width="10" height="10" rx="0.5"/>',                                                          // 挂上墙/画框
    share:   '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4"/>',                          // 分享
    pin:     '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="2.6"/>',                                                                      // 钉点评
    danmaku: '<path d="M21 15a2 2 0 0 1-2 2H8l-4 4V5a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2Z"/><path d="M8 9h8M8 13h5"/>',                                                              // 弹幕/众声
    collapse:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M15 3v18"/>',                                                                                          // 收起解读(右栏)
    music:   '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="2.6"/><circle cx="18" cy="16" r="2.6"/>',                                                                    // 背景音乐
    musicOff:'<path d="M9 18V5l12-2v4"/><circle cx="6" cy="18" r="2.6"/><path d="M3 3l18 18"/>',                                                                                // 背景音乐 关
    more:    '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',                                                              // 更多(横向展开)
    heart:   '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/>',                    // 收藏
    chevron: '<path d="m6 9 6 6 6-6"/>',                                                                                                                                          // 展开/收起
    sound:   '<path d="M11 5 6 9H2v6h4l5 4Z"/><path d="M19 12a7 7 0 0 0-3-5.7M16 9a3.5 3.5 0 0 1 0 6"/>',                                                                        // 朗读/听
    archive: '<rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8"/><path d="M10 12h4"/>',
    home: '<path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8" /> <path d="M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />',
    search: '<path d="m21 21-4.34-4.34" /> <circle cx="11" cy="11" r="8" />',
    create: '<path d="M12 22a1 1 0 0 1 0-20 10 9 0 0 1 10 9 5 5 0 0 1-5 5h-2.25a1.75 1.75 0 0 0-1.4 2.8l.3.4a1.75 1.75 0 0 1-1.4 2.8z" /> <circle cx="13.5" cy="6.5" r=".5" fill="currentColor" /> <circle cx="17.5" cy="10.5" r=".5" fill="currentColor" /> <circle cx="6.5" cy="12.5" r=".5" fill="currentColor" /> <circle cx="8.5" cy="7.5" r=".5" fill="currentColor" />',
    me: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" /> <circle cx="12" cy="7" r="4" />',
    artists: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /> <path d="M16 3.128a4 4 0 0 1 0 7.744" /> <path d="M22 21v-2a4 4 0 0 0-3-3.87" /> <circle cx="9" cy="7" r="4" />',
    wander: '<path d="M4 16v-2.38C4 11.5 2.97 10.5 3 8c.03-2.72 1.49-6 4.5-6C9.37 2 10 3.8 10 5.5c0 3.11-2 5.66-2 8.68V16a2 2 0 1 1-4 0Z" /> <path d="M20 20v-2.38c0-2.12 1.03-3.12 1-5.62-.03-2.72-1.49-6-4.5-6C14.63 6 14 7.8 14 9.5c0 3.11 2 5.66 2 8.68V20a2 2 0 1 0 4 0Z" /> <path d="M16 17h4" /> <path d="M4 13h4" />',
    graph: '<circle cx="18" cy="5" r="3" /> <circle cx="6" cy="12" r="3" /> <circle cx="18" cy="19" r="3" /> <line x1="8.59" x2="15.42" y1="13.51" y2="17.49" /> <line x1="15.41" x2="8.59" y1="6.51" y2="10.49" />',
    worldview: '<circle cx="12" cy="12" r="10" /> <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" /> <path d="M2 12h20" />',
    works: '<rect width="18" height="18" x="3" y="3" rx="2" ry="2" /> <circle cx="9" cy="9" r="2" /> <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />',
    gallery: '<path d="m22 11-1.296-1.296a2.4 2.4 0 0 0-3.408 0L11 16" /> <path d="M4 8a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2" /> <circle cx="13" cy="7" r="1" fill="currentColor" /> <rect x="8" y="2" width="14" height="14" rx="2" />',
    forces: '<path d="M12.8 19.6A2 2 0 1 0 14 16H2" /> <path d="M17.5 8a2.5 2.5 0 1 1 2 4H2" /> <path d="M9.8 4.4A2 2 0 1 1 11 8H2" />',
    compass: '<circle cx="12" cy="12" r="10" /> <path d="m16.24 7.76-1.804 5.411a2 2 0 0 1-1.265 1.265L7.76 16.24l1.804-5.411a2 2 0 0 1 1.265-1.265z" />',
    subject: '<path d="M13.172 2a2 2 0 0 1 1.414.586l6.71 6.71a2.4 2.4 0 0 1 0 3.408l-4.592 4.592a2.4 2.4 0 0 1-3.408 0l-6.71-6.71A2 2 0 0 1 6 9.172V3a1 1 0 0 1 1-1z" /> <path d="M2 7v6.172a2 2 0 0 0 .586 1.414l6.71 6.71a2.4 2.4 0 0 0 3.191.193" /> <circle cx="10.5" cy="6.5" r=".5" fill="currentColor" />',
    tag: '<path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z" /> <circle cx="7.5" cy="7.5" r=".5" fill="currentColor" />',
    timeline: '<circle cx="12" cy="12" r="10" /> <path d="M12 6v6l4 2" />',
    data: '<ellipse cx="12" cy="5" rx="9" ry="3" /> <path d="M3 5V19A9 3 0 0 0 21 19V5" /> <path d="M3 12A9 3 0 0 0 21 12" />',
    dashboard: '<rect width="7" height="9" x="3" y="3" rx="1" /> <rect width="7" height="5" x="14" y="3" rx="1" /> <rect width="7" height="9" x="14" y="12" rx="1" /> <rect width="7" height="5" x="3" y="16" rx="1" />',
    sitemap: '<path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z" /> <path d="M15 5.764v15" /> <path d="M9 3.236v15" />',
    about: '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z" /> <path d="M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12" /> <path d="M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17" />',
    sparkles: '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z" /> <path d="M20 2v4" /> <path d="M22 4h-4" /> <circle cx="4" cy="20" r="2" />',
    info: '<circle cx="12" cy="12" r="10" /> <path d="M12 16v-4" /> <path d="M12 8h.01" />',
    brush: '<path d="m11 10 3 3" /> <path d="M6.5 21A3.5 3.5 0 1 0 3 17.5a2.62 2.62 0 0 1-.708 1.792A1 1 0 0 0 3 21z" /> <path d="M9.969 17.031 21.378 5.624a1 1 0 0 0-3.002-3.002L6.967 14.031" />',
    design: '<path d="M11 17a4 4 0 0 1-8 0V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2Z" /> <path d="M16.7 13H19a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H7" /> <path d="M 7 17h.01" /> <path d="m11 8 2.3-2.3a2.4 2.4 0 0 1 3.404.004L18.6 7.6a2.4 2.4 0 0 1 .026 3.434L9.9 19.8" />',
    network: '<rect x="16" y="16" width="6" height="6" rx="1" /> <rect x="2" y="16" width="6" height="6" rx="1" /> <rect x="9" y="2" width="6" height="6" rx="1" /> <path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3" /> <path d="M12 12V8" />',
    arrowLeft: '<path d="m12 19-7-7 7-7" /> <path d="M19 12H5" />',
    arrowRight: '<path d="M5 12h14" /> <path d="m12 5 7 7-7 7" />',
    chevronRight: '<path d="m9 18 6-6-6-6" />',
    history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" /> <path d="M3 3v5h5" /> <path d="M12 7v5l4 2" />'                                          // 数据档案
  };
  function svg(name, o){
    o = o || {};
    var d = P[name]; if(!d) return '';
    var sw = o.sw || 1.7, fill = o.fill ? 'currentColor' : 'none';
    return '<svg class="ico ico-'+name+'" viewBox="0 0 24 24" width="1em" height="1em" fill="'+fill+'" stroke="currentColor" '+
           'stroke-width="'+sw+'" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+d+'</svg>';
  }
  return { svg: svg, paths: P };
})();

/* 静态页便捷用法:<i data-ic="me"></i> 自动替换为图标;
   data-ic-fill = 实心;data-ic-text="搜索" = 图标后跟文字。一行 script 即可全页生效。 */
(function(){
  function mount(){
    document.querySelectorAll('[data-ic]').forEach(function(el){
      if(el.__ic)return;el.__ic=1;
      var t=el.getAttribute('data-ic-text');
      el.innerHTML=AHAIcons.svg(el.getAttribute('data-ic'),{fill:el.hasAttribute('data-ic-fill')})+(t?' <span>'+t+'</span>':'');
      var d=getComputedStyle(el).display;if(d==='inline')el.style.display='inline-flex';
      el.style.alignItems='center';if(t)el.style.gap=el.style.gap||'6px';
    });
  }
  window.AHAIconsMount=mount;
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();
