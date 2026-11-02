const test=require('node:test'),assert=require('node:assert/strict'),{createEngine}=require('../backend/frame-engine.cjs');
test('frame summary preserves manual precedence and .8 review boundary',async()=>{
 const e=await createEngine([],{manual:'gilt'}),works=[{file:'manual'},{file:'missing'},{file:'low',frame_suggest:'wood',frame_conf:.79},{file:'edge',frame_suggest:'wood',frame_conf:.8}];
 const s=e.summarize(works);assert.equal(s.total,4);assert.equal(s.human_count,1);assert.equal(s.review_count,2);assert.equal(s.stats.fc.gilt,1);assert.equal(Object.values(s.stats.fc).reduce((a,b)=>a+b),4);assert.equal(Object.values(s.stats.conf).reduce((a,b)=>a+b),3);
 assert.equal(e.review(works[0]),false);assert.equal(e.review(works[3]),false);
});
