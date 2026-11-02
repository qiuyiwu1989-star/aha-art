const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/../web/museum.html','utf8');const art=fs.readFileSync(__dirname+'/../web/art.html','utf8');
const ctx=vm.createContext({AbortController,window:{},clearInterval,URLSearchParams});
vm.runInContext(source.slice(source.indexOf('let viewController='),source.indexOf('function section(')),ctx);
vm.runInContext('old=viewController.signal;count=0;viewCleanups.push(()=>count++);disposeView()',ctx);assert.equal(vm.runInContext('old.aborted && !viewController.signal.aborted && count===1',ctx),true);
const works=[{work_id:42,file:'img/中国%20画.jpg'}];const ac=vm.createContext({URLSearchParams,WORKS:works,byFile:{[works[0].file]:works[0]},location:{search:'?id=42'}});vm.runInContext(art.slice(art.indexOf('function qWork()'),art.indexOf('function cleanTitle(')),ac);assert.equal(vm.runInContext('qWork().work_id',ac),42);ac.location.search='?w='+encodeURIComponent(works[0].file);assert.equal(vm.runInContext('qWork().work_id',ac),42);ac.location.search='?w='+encodeURIComponent(encodeURIComponent(works[0].file));assert.equal(vm.runInContext('qWork().work_id',ac),42);
// Run the actual infinite-feed controller: no eager load; repeated intersections
// coalesce, pages append without losing earlier works, errors require explicit retry.
(async()=>{
 let calls=[],resolve,reject,observer,added=0,cleanups=[];
 const status={innerHTML:'',setAttribute(){},querySelector(){return this.retry||(this.retry={})}};
 const work=[{work_id:1,file:'one'}];
 const pc=vm.createContext({URLSearchParams,Set,homeFeedState:null,saveHomeFeed(){},viewController:new AbortController(),HOME:{next_cursor:'c1',has_more:true},WORKS:work,
 CAT:u=>{calls.push(u);return new Promise((a,b)=>{resolve=a;reject=b})},allSec:{isConnected:true,querySelector:()=>status},registerWorks(){},buildCols(){},addBatch:n=>added+=n,
 viewCleanups:cleanups,onView(){},window:{},clearTimeout,setTimeout,
 IntersectionObserver:class{constructor(fn){observer=this;this.fn=fn}observe(){}unobserve(){}disconnect(){this.closed=true}},colCount:()=>2,_colN:2,relayout(){}});
 const start=source.indexOf("  const moreWrap=allSec.querySelector('#moreWrap')"),end=source.indexOf('\n}\n// 缩略图省带宽:',start);
 vm.runInContext(source.slice(start,end),pc);assert.equal(calls.length,0);
 observer.fn([{isIntersecting:true}]);observer.fn([{isIntersecting:true}]);assert.equal(calls.length,1);assert.match(calls[0],/cursor=c1/);
 resolve({items:[{work_id:1},{work_id:2,file:'two'}],has_more:true,next_cursor:'c2'});await new Promise(setImmediate);
 assert.equal(work.length,2);assert.equal(added,25);assert.equal(work[0].file,'one');
 observer.fn([{isIntersecting:true}]);reject(new Error('offline'));await new Promise(setImmediate);
 observer.fn([{isIntersecting:true}]);assert.equal(calls.length,2);assert.match(status.innerHTML,/重试/);
 status.retry.onclick();assert.equal(calls.length,3);assert.match(calls[2],/cursor=c2/);
 resolve({items:[{work_id:3,file:'three'}],has_more:false,next_cursor:null});await new Promise(setImmediate);
 observer.fn([{isIntersecting:true}]);assert.equal(calls.length,3);assert.equal(work.length,3);assert.match(status.innerHTML,/已看完/);
 cleanups.forEach(f=>f());assert(observer.closed);
 console.log('PASS route cleanup, legacy links, lazy infinite feed, append/dedupe, single flight, retry, end state, disposal');
})().catch(e=>{console.error(e);process.exitCode=1});
