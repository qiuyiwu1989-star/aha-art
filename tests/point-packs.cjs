const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const ctx={window:{},fetch:async()=>({ok:false,status:503})};vm.createContext(ctx);vm.runInContext(fs.readFileSync('web/js/aha-point-pack.js','utf8'),ctx);
for(const name of ['points','affect'])test(name+' every decoded record equals source',()=>{
 const source=JSON.parse(fs.readFileSync(`web/data/live/${name}.json`));const pack=JSON.parse(fs.readFileSync(`web/data/live/${name}.pack.json`));
 const decoded=JSON.parse(JSON.stringify(ctx.window.AHAPointPack.decode(pack)));assert.deepEqual(decoded,source);assert.equal(decoded.points.length,20000);
});
test('pack rejects HTTP error without original package fallback',async()=>{await assert.rejects(ctx.window.AHAPointPack.load('x'),/503/);});
