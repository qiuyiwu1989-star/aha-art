const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
function load(file,extra={}){let window={location:{href:'http://localhost/',origin:'http://localhost'}};vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/js',file),'utf8'),{window,URL,Map,AbortController,DOMException,setTimeout,clearTimeout,...extra});return window;}
test('TIFF gets bounded WebP, previous transform replaced, static preserved',()=>{
let a=load('aha-images.js').AHAImages;
let u=a.url('/img/a.tiff?imageMogr2/thumbnail/9999x&v=2',{size:9999});
assert.match(u,/thumbnail\/1600x1600\/format\/webp/);
assert.equal((u.match(/imageMogr2/g)||[]).length,1);
assert.match(u,/v=2/);
assert.equal(a.url('/static/a.jpg'),'/static/a.jpg');
});
test('GET deduplicates concurrent calls and propagates HTTP failure',async()=>{
let count=0;let a=load('aha-request.js',{fetch:async()=>{count++;return {ok:false,status:503};}}).AHARequest;
let p=a.get('/cat');assert.equal(p,a.get('/cat'));
await assert.rejects(p,/503/);assert.equal(count,1);
await assert.rejects(a.get('/cat'),/503/);assert.equal(count,2);
});
test('caller cancellation reaches fetch',async()=>{
let a=load('aha-request.js',{fetch:(_u,{signal})=>new Promise((_r,reject)=>signal.addEventListener('abort',()=>reject(signal.reason)))}).AHARequest;
let c=new AbortController();let p=a.get('/cat',{signal:c.signal});c.abort();await assert.rejects(p,{name:'AbortError'});
});
test('cancelled independent consumer does not abort shared request',async()=>{
let calls=[];let a=load('aha-request.js',{fetch:(url,{signal})=>new Promise((resolve,reject)=>{calls.push({resolve,signal});signal.addEventListener('abort',()=>reject(signal.reason));})}).AHARequest;
let shared=a.get('/same'),other=a.get('/same');let c=new AbortController();let independent=a.get('/same',{signal:c.signal});c.abort();await assert.rejects(independent);assert.equal(calls[0].signal.aborted,false);calls[0].resolve({ok:true,json:()=>({ok:true})});await shared;await other;
});
test('completed request clears timeout',async()=>{
let clears=0;let a=load('aha-request.js',{setTimeout:()=>42,clearTimeout:id=>{assert.equal(id,42);clears++;},fetch:async()=>({ok:true,json:()=>({})})}).AHARequest;
await a.get('/done');assert.equal(clears,1);
});
test('image guard handles repeated source failures and removes srcset',()=>{
let handlers={};let attrs={src:'/first.jpg',srcset:'huge.jpg 2x',sizes:'100vw'};
let im={tagName:'IMG',style:{},alt:'',getAttribute:k=>attrs[k],setAttribute:(k,v)=>attrs[k]=v,removeAttribute:k=>delete attrs[k],set src(v){attrs.src=v;}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/js/imgguard.js'),'utf8'),{window:{addEventListener:()=>{}},document:{readyState:'loading',addEventListener:(n,f)=>handlers[n]=f},encodeURIComponent});
handlers.error({target:im});assert.match(attrs.src,/^data:/);assert.equal(attrs.srcset,undefined);
attrs.src='/second.jpg';attrs.srcset='second-huge.jpg 2x';handlers.error({target:im});assert.match(attrs.src,/^data:/);assert.equal(attrs.srcset,undefined);
});
test('memory writes return explicit failure without retry',async()=>{
let count=0,window={};vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/aha-mem.js'),'utf8'),{window,localStorage:{getItem:()=> 'test'},fetch:async()=>{count++;return {ok:false,status:503};},Math,Date,encodeURIComponent});
let result=await window.AHA.collect(1,true);assert.equal(result.ok,false);assert.match(result.error,/503/);assert.equal(count,1);
});
