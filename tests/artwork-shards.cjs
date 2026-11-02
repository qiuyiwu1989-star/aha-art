const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('web/kg-artworks-live.html','utf8');
const body=html.slice(html.indexOf('const detailShards='),html.indexOf('function openM(a)'));
test('every source and index record resolves to exact detail shard',()=>{
 const full=JSON.parse(fs.readFileSync('web/data/live/artworks_v2.json')).artworks;
 const index=JSON.parse(fs.readFileSync('web/data/live/artworks_index.json')).artworks;
 let n=0;
 for(const [slug,record] of Object.entries(full)){
  let hash=0;for(let i=0;i<slug.length;i++)hash=(Math.imul(hash,31)+slug.charCodeAt(i))>>>0;
  const shard=JSON.parse(fs.readFileSync(`web/data/live/artwork-details/${hash%64}.json`));
  assert.deepEqual(shard[slug],record);assert.ok(index[slug]);n++;
 }assert.equal(n,4000);assert.equal(Object.keys(index).length,n);
});
test('detail cache deduplicates, retries failures, bounds memory',async()=>{
 let calls=0,fail=true;
 const ctx={Map,Math,fetch:async()=>{calls++;return {ok:!fail,status:503,json:async()=>({ok:1})}}};vm.createContext(ctx);vm.runInContext(body,ctx);
 const a=ctx.ensureFull('1'),b=ctx.ensureFull('1');assert.equal(a,b);await assert.rejects(a);assert.equal(calls,1);
 fail=false;await ctx.ensureFull('1');assert.equal(calls,2);
 for(let i=2;i<40;i++)await ctx.ensureFull(String(i));
 assert.ok(vm.runInContext('detailShards.size',ctx)<=8);
});
