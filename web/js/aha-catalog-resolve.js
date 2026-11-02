/* Resolve only metadata referenced by the current personal record, never the catalog. */
window.AHACatalog={async resolve(keys){
 const unique=[...new Set(keys.filter(k=>k!==null&&k!==undefined&&k!=='' ).map(String))],works=[],matches={};
 for(let i=0;i<unique.length;i+=60){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
  try{const r=await fetch('/cat/resolve?'+new URLSearchParams({keys:JSON.stringify(unique.slice(i,i+60))}),{signal:controller.signal});
   if(!r.ok)throw Error('作品信息加载失败');const d=await r.json();works.push(...(d.items||[]));Object.assign(matches,d.matches||{});
  }finally{clearTimeout(timer);}
 }
 return {works,matches};
}};
