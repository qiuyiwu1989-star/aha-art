/* aha · 画框 / 装裱系统 ————————————————————————————————————
   显示优先级:  本页试装预览(session) > 馆方规范化(canonical, 服务端) > 自动匹配
   AHAFrames.pick(work)         → 该画此刻应挂的框 key
   AHAFrames.auto(work)         → 仅自动匹配(看元数据),返回 key 字符串
   AHAFrames.autoExplain(work)  → {key, conf:'high|mid|low|none', why} 带置信与理由
   AHAFrames.wrap(imgHTML,w,ex) → 带框 DOM 字符串
   AHAFrames.loadStyles()       → Promise,拉框样式目录(api/frame_styles),叠加 名字/sku/匹配规则
   AHAFrames.loadCanonical()    → Promise,拉馆方统一指定的框(api/frames)
   AHAFrames.saveCanonical(file,key,pass) → Promise,馆方设/清某画的框(api/frame/save,需口令)
   AHAFrames.setPreview/getPreview(file[,key]) → 本页试装(不落库,刷新即还原)
   单一事实源:CSS = css/aha-frames.css;目录/匹配规则/供应链 = DB mu_frame_style(后台 dashboard 管理)。
   说明页 = frames.html */
window.AHAFrames = (function(){
  // 内置兜底:DB 不可用 / 未加载时,auto() 仍按这套规则工作。DB 会叠加覆盖 name/sku/匹配规则等。
  // match_style=流派关键词;match_media=媒材「硬规则」关键词(不论流派都钉死该框);priority 越小越先判。
  var STYLES = [
    {key:'wood',   name:'素木暖框', emoji:'🪵', desc:'温润胡桃木 · 大多数油画的稳妥选择',
     sku:'AHA-FRM-WOOD-01', priority:60, match_style:'浪漫主义,现实主义,写实,印象派,后印象,新印象,巴比松,哈德逊河,自然主义,象征主义,纳比派,外光派,风俗', match_media:''},
    {key:'gilt',   name:'金箔古典', emoji:'🏛️', desc:'描金雕花 · 古典 / 巴洛克 / 文艺复兴的庙堂气',
     sku:'AHA-FRM-GILT-01', priority:50, match_style:'文艺复兴,巴洛克,古典主义,新古典,洛可可,矫饰主义,矫饰,风格主义,样式主义,学院,唯美主义,哥特,拜占庭,宗教,威尼斯画派,弗拉芒', match_media:'蛋彩,坦培拉,木板,湿壁画,fresco,金属,珐琅'},
    {key:'noir',   name:'黑漆细框', emoji:'⬛', desc:'细黑边宽卡纸 · 现代与摄影感',
     sku:'AHA-FRM-NOIR-01', priority:20, match_style:'极简,观念', match_media:'摄影,照片,银盐,gelatin,photograph'},
    {key:'mat',    name:'白卡宽边', emoji:'🤍', desc:'宽白卡纸 · 纸本 / 版画 / 素描 / 浅色',
     sku:'AHA-FRM-MAT-01', priority:30, match_style:'', match_media:'版画,蚀刻,石版,木刻,铜版,丝网,珂罗版,素描,水彩,炭笔,色粉,插画,纸本'},
    {key:'white',  name:'素白馆藏', emoji:'◻️', desc:'暖纸薄边 · 干净中性 · 书画 / 册页 / 通用陈列',
     sku:'AHA-FRM-WHITE-01', priority:95, match_style:'', match_media:''},
    {key:'silver', name:'冷银',     emoji:'⚪', desc:'冷调银灰 · 蓝绿色调作品',
     sku:'AHA-FRM-SILVER-01', priority:90, match_style:'', match_media:''},
    {key:'scroll', name:'卷轴朱漆', emoji:'🏮', desc:'丝绢底朱漆木 · 东方水墨 / 写意 / 留白',
     sku:'AHA-FRM-SCROLL-01', priority:10, match_style:'院体,文人画,文人,青绿,没骨,界画,浙派,吴门,写意,工笔', match_media:'水墨,绢本,设色,册页,手卷,挂轴,纸本水墨'},
    {key:'float',  name:'亚克力浮裱', emoji:'▫️', desc:'亚克力面封 · 当代 / 抽象的高光泽悬浮',
     sku:'AHA-FRM-FLOAT-01', priority:40, match_style:'抽象,构成,极简,波普,超现实,立体主义,未来主义,表现主义,野兽派,新艺术运动,素朴艺术,当代,现代主义,色域,达达,观念,光效应,硬边', match_media:''}
  ];
  var BY = {}; STYLES.forEach(function(s){ BY[s.key]=s; });
  var _styles = null;   // 框样式目录(DB,api/frame_styles 拉到后填),null=未加载
  var _canon = {};      // 馆方规范化:work_id -> key
  var _preview = {};    // 本页试装(session,不落库)

  // 世界观(WV1–6)是「情绪/认知」范畴,不是文化 origin。
  // 切忌拿世界观中文名做关键词正则:「写意寄情」含『写意』会误伤洛可可西画、
  // 「表现外化」含『表现』会漏进无框。东方与否只看真实地理 origin + 真东方画种术语。
  var EAST_REGION = /(^|[^a-z])(east|asia|asian|china|chinese|japan|japanese|korea|korean|tokyo|kyoto|beijing|shanghai)([^a-z]|$)/i;
  var EAST_CJK    = /中国|中華|中华|日本|韩国|韓國|朝鲜|越南|印度|泰国|蒙古|台湾|香港|澳门|安徽|江苏|浙江|北京|上海|山东|河南|广东|四川|陕西|山西|湖南|湖北|福建|江西|河北|辽宁|吉林|黑龙江|云南|贵州|甘肃|广西|内蒙|新疆|西藏|宁夏|青海|海南|天津|重庆|苏州|杭州|扬州|金陵|萧县/;
  // 真东方画种术语(不含跨文化情绪词,故安全):
  var EAST_STYLE  = /水墨|工笔|院体|文人画|青绿|没骨|界画|册页|手卷|挂轴/;
  function isEast(w){
    if(!w) return false;
    var r = (w.region||'');
    if(EAST_REGION.test(r) || EAST_CJK.test(r)) return true;
    return EAST_STYLE.test((w.style||'')+' '+(w.medium||w.media||''));
  }

  function _kw(s){ return (s||'').split(/[,，|]/).map(function(x){return x.trim();}).filter(Boolean); }
  function _hit(text, kws){ text=(text||''); for(var i=0;i<kws.length;i++){ if(text.indexOf(kws[i])>=0) return true; } return false; }

  // 画面色温(从主色 HSV 粗判):暖(红橙黄)/冷(青蓝紫)/中
  function _colorTemp(w){
    var c=(w.color||{}); if(typeof c.h!=='number') return null;
    if(c.h>=20 && c.h<=70) return 'warm';
    if(c.h>=170 && c.h<=270) return 'cool';
    return 'neutral';
  }
  // 关联度打分:吃框目录预留的 match_rule(加权多维 era/medium/subject/region + color_temp),
  // 对每框算与这幅画的关联分,取最高。这是「确定性匹配层」(LLM 策展之下、原始关键词之上)。
  function scoreByRule(w){
    var fields={era:(w.style||''), medium:(w.medium||w.media||''), subject:(w.subject||''), region:(w.region||'')};
    var ct=_colorTemp(w), best=null;
    STYLES.forEach(function(s){
      if(s.active===false) return;
      var mr=s.match_rule; if(!mr||!mr.dims) return;
      var sc=0, hits=[], strong=false;
      for(var dim in fields){
        var vals=mr.dims[dim]; if(!vals||!vals.length) continue;
        var text=fields[dim]; if(!text) continue;
        var bv=0, bl='';
        for(var i=0;i<vals.length;i++){ var w0=(vals[i].w||1); if(text.indexOf(vals[i].v)>=0 && w0>bv){ bv=w0; bl=vals[i].v; } }
        if(bv>0){ sc+=bv; if(dim==='era'||dim==='medium'){ strong=true; hits.unshift(bl); } else hits.push(bl); }
      }
      if(ct && mr.color_temp && mr.color_temp!=='any' && mr.color_temp===ct) sc+=0.4;
      sc *= (mr.propensity||1);
      if(sc>0 && (!best || sc>best.score)) best={key:s.key, score:sc, strong:strong, why:hits.slice(0,3).join(' · ')||'关联度'};
    });
    return best;
  }

  // 自动匹配(分层,带置信):LLM策展 > 东方 > 关联度打分(match_rule) > 色彩兜底 > 待定。
  function autoExplain(w){
    if(!w) return {key:'wood', conf:'none', why:'无作品'};
    // LLM 逐画装裱策展(frame_curate)优先——它读了画面内容,最细腻
    if(w.frame_suggest && BY[w.frame_suggest])
      return {key:w.frame_suggest, conf:'high', src:'llm',
              why:(w.frame_why||'AI 按画面内容策展'), finish:(w.frame_finish||'')};
    if(isEast(w)) return {key:'scroll', conf:'high', src:'rule', why:'东方'};
    // 关联度打分(吃预留 match_rule);DB 无 match_rule 时回落老关键词规则
    var best=scoreByRule(w);
    if(best) return {key:best.key, conf:(best.strong?'high':'mid'), src:'rule', why:best.why};
    var style=(w.style||''), media=(w.medium||w.media||'');
    var ordered = STYLES.slice().sort(function(a,b){ return (a.priority||50)-(b.priority||50); });
    for(var i=0;i<ordered.length;i++){
      var s=ordered[i];
      if(media && _hit(media,_kw(s.match_media))) return {key:s.key, conf:'high', src:'rule', why:'媒材 · '+media};
      if(style && _hit(style,_kw(s.match_style))) return {key:s.key, conf:'high', src:'rule', why:'流派 · '+style};
    }
    var c=(w.color||{});
    if(typeof c.h==='number'){
      if((c.s==null||c.s<0.18) && c.v>0.72) return {key:'mat', conf:'mid', why:'浅色纸感(色彩兜底)'};
      if(c.h>=150 && c.h<=255 && (c.s||0)>0.14) return {key:'silver', conf:'mid', why:'蓝绿冷调(色彩兜底)'};
    } else if(typeof c.v==='number' && c.v>0.82 && (c.s||0)<0.25){
      return {key:'mat', conf:'mid', why:'浅色(色彩兜底)'};
    }
    var has=(style||media);
    return {key:'wood', conf:has?'low':'none', why:has?'流派/媒材未命中规则':'无流派/媒材信号 · 待定'};
  }
  function auto(w){ return autoExplain(w).key; }   // 向后兼容:返回 key 字符串

  function pick(w){
    if(!w) return 'wood';
    var f=w.file;
    if(_preview[f] && BY[_preview[f]]) return _preview[f];      // 本页试装
    if(_canon[f] && BY[_canon[f]]) return _canon[f];            // 馆方人工指定
    if(w.frame_suggest && BY[w.frame_suggest]) return w.frame_suggest;  // LLM 逐画策展
    return auto(w);                                             // 关键词兜底
  }
  function canonOf(file){ return _canon[file]||''; }
  function getPreview(file){ return _preview[file]||''; }
  function setPreview(file,key){ if(key&&BY[key]) _preview[file]=key; else delete _preview[file]; }
  // 向后兼容旧调用名
  function getOverride(file){ return getPreview(file); }
  function setOverride(file,key){ setPreview(file,key); }

  function _api(path){ return 'api/'+path; }   // 相对路径,两域名通(nginx /api/→8093)
  // 拉框样式目录:把 DB 的 名字/emoji/desc/sku/匹配规则/sort/active 叠加到内置 STYLES 上。
  // active=false 的从公开展示中剔除(但 auto() 规则仍生效——下架≠停用匹配)。
  function loadStyles(){
    return fetch(_api('frame_styles')).then(function(r){return r.json();}).then(function(d){
      var rows=(d&&d.styles)||[]; if(!rows.length) return STYLES;
      var byKey={}; rows.forEach(function(s){ byKey[s.key]=s; });
      STYLES.forEach(function(s){
        var o=byKey[s.key]; if(!o) return;
        s.name=o.name||s.name; s.emoji=o.emoji||s.emoji; if(o.descr) s.desc=o.descr;
        s.sku=o.sku||s.sku; s.css_note=o.css_note; s.material=o.material; s.supplier=o.supplier;
        s.price_cents=o.price_cents; s.sort=o.sort; s.active=o.active!==false;
        if(o.match_style!=null) s.match_style=o.match_style;
        if(o.match_media!=null) s.match_media=o.match_media;
        if(o.match_rule!=null) s.match_rule=o.match_rule;   // 关联度(加权多维),打分匹配吃它
        if(o.priority!=null) s.priority=o.priority;
      });
      STYLES.sort(function(a,b){ return (a.sort||0)-(b.sort||0); });
      _styles=rows; return STYLES;
    }).catch(function(){ return STYLES; });
  }
  // 公开展示用的样式列表(过滤下架),后台/匹配仍用全量 STYLES。
  function visibleStyles(){ return STYLES.filter(function(s){ return s.active!==false; }); }

  function loadCanonical(){
    return fetch(_api('frames')).then(function(r){return r.json();})
      .then(function(d){ _canon = (d&&d.frames)||{}; return _canon; })
      .catch(function(){ _canon={}; return _canon; });
  }
  function saveCanonical(file,key,pass){
    return fetch(_api('frame/save'),{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({work:file,frame:key||'',pass:pass||''})})
      .then(function(r){return r.json();})
      .then(function(d){ if(d&&d.ok){ if(key) _canon[file]=key; else delete _canon[file]; } return d; });
  }

  function cls(w, extra){ return 'aha-frame f-'+pick(w)+(extra?(' '+extra):''); }
  function wrap(imgHTML, w, extra){
    return '<div class="'+cls(w,extra)+'"><div class="aha-mat">'+imgHTML+'</div></div>';
  }
  return { STYLES:STYLES, BY:BY, auto:auto, autoExplain:autoExplain, pick:pick, cls:cls, wrap:wrap, isEast:isEast,
           loadStyles:loadStyles, visibleStyles:visibleStyles,
           loadCanonical:loadCanonical, saveCanonical:saveCanonical, canonOf:canonOf,
           getPreview:getPreview, setPreview:setPreview,
           getOverride:getOverride, setOverride:setOverride };
})();
