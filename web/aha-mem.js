/* aha 匿名记忆客户端 · 所有页面引入 <script src="aha-mem.js"></script>
   提供 window.AHA:uid(localStorage)+ 行为/收藏/评分/口味/策展 API。
   相对路径 api/ → 两域名都通(根域名 /api/,子路径 /aha/api/)。 */
(function () {
  var KEY = 'aha_uid';
  var uid = null;
  try { uid = localStorage.getItem(KEY); } catch (e) {}
  if (!uid) {
    uid = 'u_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
    try { localStorage.setItem(KEY, uid); } catch (e) {}
  }
  function json(r) { if (!r.ok) { var e = new Error('HTTP ' + r.status); e.status=r.status; throw e; } return r.json(); }
  function read(url) { return window.AHARequest ? window.AHARequest.get(url) : fetch(url).then(json); }
  function post(path, body) {
    return fetch('api/' + path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ uid: uid }, body || {}))
    }).then(json).catch(function(e){ return {ok:false,error:e.message}; });
  }
  function get(path) {
    var sep = path.indexOf('?') >= 0 ? '&' : '?';
    return read('api/' + path + sep + 'uid=' + encodeURIComponent(uid));
  }
  window.AHA = {
    uid: uid,
    // kind: open/dwell/like/collect/skip/enter_hall/gen/view ; o:{target_type,target_id,x,y,dwell_ms}
    event: function (kind, o) { return post('me/event', Object.assign({ kind: kind }, o || {})).catch(function(e){return {ok:false,error:e.message};}); },
    collect: function (work_id, on) { return post('me/collect', { work_id: work_id, on: on }); },
    rate: function (target_id, rating) { return post('me/rate', { target_id: target_id, rating: rating }); },
    state: function () { return get('me/state'); },
    hot: function () { return read('api/hot'); },
    saveExhibition: function (title, note, work_ids, pub, rule, id) { return post('me/exhibition', { title: title, note: note, work_ids: work_ids, public: !!pub, rule: rule || null, id: id || null }); },
    deleteExhibition: function (id) { return post('me/exhibition/delete', { id: id }); },
    myExhibitions: function () { return get('me/exhibitions'); }
  };
})();
