const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('bounded thumbnail retries same URL once then terminates',()=>{
 let handlers={},timers=[],attrs={src:'/img/a.jpg?imageMogr2/thumbnail/640x640/format/webp'},writes=[];
 const original=attrs.src,im={tagName:'IMG',style:{},isConnected:true,getAttribute:k=>attrs[k],setAttribute:(k,v)=>attrs[k]=v,removeAttribute:k=>delete attrs[k],set src(v){writes.push(v);attrs.src=v;}};
 vm.runInNewContext(fs.readFileSync('web/js/imgguard.js','utf8'),{window:{addEventListener(){}},document:{readyState:'loading',addEventListener:(n,f)=>handlers[n]=f},setTimeout:(f,ms)=>{assert.equal(ms,800);timers.push(f)},WeakMap,encodeURIComponent});
 handlers.error({target:im});handlers.error({target:im});assert.equal(timers.length,1);assert.equal(writes.length,0);
 timers[0]();assert.equal(writes[0],original);handlers.error({target:im});assert.match(attrs.src,/^data:/);handlers.error({target:im});assert.equal(timers.length,1);assert.equal(writes.length,2);
});
