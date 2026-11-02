const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
test('resolve fetches only referenced keys in bounded batches and rejects failed metadata',async()=>{
 const batches=[],ctx={window:{},URLSearchParams,AbortController,setTimeout,clearTimeout,fetch:async url=>{const keys=JSON.parse(new URL('http://local'+url).searchParams.get('keys'));batches.push(keys);return {ok:true,json:async()=>({items:keys.map(work_id=>({work_id}))})};}};
 vm.runInNewContext(fs.readFileSync('web/js/aha-catalog-resolve.js','utf8'),ctx);
 const result=await ctx.window.AHACatalog.resolve([...Array(125).keys(),0,null,'']);
 assert.deepEqual(batches.map(b=>b.length),[60,60,5]);assert.equal(result.works.length,125);
 ctx.fetch=async()=>({ok:false});await assert.rejects(ctx.window.AHACatalog.resolve(['missing']));
});

test('resolve preserves encoded historical keys and server alias map',async()=>{
 const key='https://example.test/img/画%20作.jpg?x=1&y=2',ctx={window:{},URLSearchParams,AbortController,setTimeout,clearTimeout,fetch:async url=>{const keys=JSON.parse(new URL('http://local'+url).searchParams.get('keys'));assert.equal(keys[0],key);return {ok:true,json:async()=>({items:[{work_id:7,file:'canonical'}],matches:{[key]:7}})};}};
 vm.runInNewContext(fs.readFileSync('web/js/aha-catalog-resolve.js','utf8'),ctx);const result=await ctx.window.AHACatalog.resolve([key]);assert.equal(result.matches[key],7);
});
