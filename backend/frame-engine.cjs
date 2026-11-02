// Execute the browser's canonical frame algorithm unchanged, with isolated read-only inputs.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
async function createEngine(styles=[],canonical={}){
 const context={window:{},fetch:async url=>({ok:true,json:async()=>String(url).includes('frame_styles')?{styles}:{frames:canonical}})};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/js/frames.js'),'utf8'),context);
 const engine=context.window.AHAFrames;await engine.loadStyles();await engine.loadCanonical();
 return {explain:work=>engine.autoExplain(work),review:work=>!canonical[work.file]&&(!work.frame_suggest||(work.frame_conf!=null&&work.frame_conf<.8)),
 summarize(works){const fc={},src={ai:0,rule:0,human:0,pending:0},conf={high:0,mid:0,low:0,none:0};let review_count=0,total=0;
 for(const w of works){total++;const ax=engine.autoExplain(w),human=canonical[w.file],key=human||ax.key;fc[key]=(fc[key]||0)+1;
 if(human){src.human++;continue;}conf[ax.conf]=(conf[ax.conf]||0)+1;if(ax.src==='llm')src.ai++;else if(ax.conf==='low'||ax.conf==='none')src.pending++;else src.rule++;
 if(!w.frame_suggest||(w.frame_conf!=null&&w.frame_conf<.8))review_count++;}
 return {total,review_count,human_count:src.human,stats:{fc,src,conf}};
 }};
}
module.exports={createEngine};
