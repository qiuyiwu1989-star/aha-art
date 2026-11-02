const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('style hover raycast runs only when dirty',()=>{
 const s=fs.readFileSync('web/kg-style-3d.html','utf8');const code=s.match(/if\(mouse.x>-2&&pickDirty\)\{[^}]+\}/)[0];
 let count=0;const ctx={mouse:{x:0},pickDirty:true,pick:()=>count++};vm.createContext(ctx);
 vm.runInContext(code,ctx);vm.runInContext(code,ctx);assert.equal(count,1);
 ctx.pickDirty=true;vm.runInContext(code,ctx);assert.equal(count,2);
 for(const marker of ["controls.addEventListener('change'","function onMove(e){pickDirty=true","function applyFilter(){pickDirty=true","function onClick(){pick();"])assert.ok(s.includes(marker));
});
test('animated galaxy hover throttles to 33ms, click refreshes synchronously',()=>{
 const s=fs.readFileSync('web/kg-galaxy.html','utf8');const code=s.match(/if\(mouse.x>-2&&performance.now\(\)-lastPickTime>=33\)\{[^}]+\}/)[0];
 let now=0,count=0;const ctx={mouse:{x:0},lastPickTime:-Infinity,performance:{now:()=>now},pick:()=>count++};vm.createContext(ctx);
 for(now=0;now<=64;now+=16)vm.runInContext(code,ctx);assert.equal(count,2);assert.ok(s.includes('function onClick(){pick();'));
});
