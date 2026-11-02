/* JSON GET only. Writes deliberately have no retry or deduplication path. */
(function(g){
  var pending=new Map();
  function get(url,options){
    options=options||{};
    var timeout=Number(options.timeout)||12000;
    var key=String(url)+'|'+timeout;
    if(!options.signal && pending.has(key)) return pending.get(key);
    var controller=new AbortController();
    var external=options.signal;
    function cancel(){controller.abort(external.reason);}
    if(external){if(external.aborted) cancel();else external.addEventListener('abort',cancel,{once:true});}
    var timer=setTimeout(function(){controller.abort(new DOMException('Request timed out','TimeoutError'));},timeout);
    var promise=fetch(url,{signal:controller.signal,credentials:'same-origin'}).then(function(r){
      if(!r.ok){var error=new Error('HTTP '+r.status);error.status=r.status;throw error;}
      return r.json();
    }).finally(function(){
      clearTimeout(timer);
      if(external) external.removeEventListener('abort',cancel);
      else pending.delete(key);
    });
    if(!external) pending.set(key,promise);
    return promise;
  }
  g.AHARequest={get:get};
})(window);
