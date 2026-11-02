/* Lossless static pack decoder. No sampling or changed coordinate precision. */
(function(g){
 g.AHAPointPack={decode:function(p){
  if(p.version!==1)throw Error('Unsupported point pack');
  const points=p.present.map((present,i)=>{
   const row={};for(const j of present){const c=p.columns[j];row[p.keys[j]]=c.dictionary?c.dictionary[c.values[i]]:c.prefix!==undefined?c.prefix+c.values[i]:c.values[i];}return row;
  });return Object.assign({},p.header,{points});
 },load:async function(url){const r=await fetch(url);if(!r.ok)throw Error('HTTP '+r.status);return g.AHAPointPack.decode(await r.json());}};
})(window);
