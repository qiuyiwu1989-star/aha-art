const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const s=fs.readFileSync(__dirname+'/../web/museum.html','utf8');let callback;
const ctx=vm.createContext({IntersectionObserver:class{constructor(fn){callback=fn}disconnect(){}},viewCleanups:[]});
vm.runInContext(s.slice(s.indexOf('  const tileObserver='),s.indexOf('  function addTile(w)')),ctx);
const tile={firstElementChild:{},style:{},_builders:[()=>({image:'bounded.webp'})],appendChild(node){this.firstElementChild=node},getBoundingClientRect:()=>({height:321}),replaceChildren(){this.firstElementChild=null}};
callback([{target:tile,isIntersecting:false}]);assert.equal(tile.style.height,'321px');assert.equal(tile.firstElementChild,null);
callback([{target:tile,isIntersecting:true}]);assert.equal(tile.firstElementChild.image,'bounded.webp');assert.equal(tile.style.height,'');
let saved={items:[{work_id:7}],at:Date.now(),page:{next_cursor:'cursor'},y:900};
function restore(value){const c=vm.createContext({sessionStorage:{getItem:()=>JSON.stringify(value)},Date});vm.runInContext(s.slice(s.indexOf('let homeFeedState='),s.indexOf('function usePage(')),c);return vm.runInContext('homeFeedState',c)}
assert.equal(restore(saved).y,900);assert.equal(restore({...saved,at:0}),null);assert.equal(restore({...saved,items:Array(241).fill({})}).items.length,241);
console.log('PASS measured slot detach/restore and bounded expiring cross-document snapshot');
{
 let layoutOffset=0,resizeCallback;let scroll=100,frames=[],timers=[],cancelled=[],handlers={};const target={dataset:{workKey:'42'},style:{},getBoundingClientRect:()=>({top:1200+layoutOffset-scroll})};
 const c=vm.createContext({app:{},ResizeObserver:class{constructor(fn){resizeCallback=fn}observe(){}disconnect(){}},homeFeedState:{anchor:{key:'42',top:185},y:99},disposed:false,mason:{querySelectorAll:selector=>selector==='.feed-segment'?[]:[target]},window:{get scrollY(){return scroll}},scrollTo:(x,y)=>scroll=y,requestAnimationFrame:f=>frames.push(f),setTimeout:f=>{timers.push(f);return timers.length},clearTimeout:id=>cancelled.push(id),viewCleanups:[],onView:(target,type,fn)=>handlers[type]=fn});
 const a=s.indexOf('  if(homeFeedState){\n    const saved=');vm.runInContext(s.slice(a,s.indexOf('  viewCleanups.push(()=>{saveHomeFeed',a)),c);frames[0]();assert.equal(scroll,1015);assert.equal(target.getBoundingClientRect().top,185);assert.equal(target.style.contentVisibility,'visible');layoutOffset=192;resizeCallback();timers.at(-1)();assert.equal(target.getBoundingClientRect().top,185);handlers.wheel();assert(cancelled.includes(2));c.viewCleanups.forEach(fn=>fn());assert(cancelled.length>=3);console.log('PASS return uses selected-work viewport anchor instead of stale absolute y');
}
// 100 pages, 2400 records: only near-window segments retain image/frame DOM.
{
 const segments=Array.from({length:200},()=>({style:{},children:Array.from({length:12},()=>({image:true})),get firstElementChild(){return this.children[0]},_builders:Array.from({length:12},()=>()=>({image:true})),getBoundingClientRect:()=>({height:3600}),replaceChildren(){this.children=[]},appendChild(n){this.children.push(n)}}));
 callback(segments.map((target,i)=>({target,isIntersecting:i>=98&&i<=101})));
 assert.equal(segments.reduce((n,s)=>n+s.children.length,0),48);
 callback([{target:segments[0],isIntersecting:true},{target:segments[98],isIntersecting:false}]);
 assert.equal(segments[0].children.length,12);assert.equal(segments[98].children.length,0);
 console.log('PASS 100-page simulation: 2400 records, 200 measured segments, 48 mounted cards, reverse restoration');
}
