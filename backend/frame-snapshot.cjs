const {createEngine}=require('./frame-engine.cjs');
let input='';process.stdin.setEncoding('utf8');process.stdin.on('data',chunk=>{input+=chunk;if(input.length>128*1024*1024)throw Error('frame source exceeds budget');});
process.stdin.on('end',async()=>{try{const data=JSON.parse(input),engine=await createEngine(data.styles,data.canonical);process.stdout.write(JSON.stringify({summary:engine.summarize(data.items),review_ids:data.items.filter(w=>engine.review(w)).map(w=>w.work_id)}));}catch(e){process.stderr.write('frame snapshot failed');process.exitCode=1;}});
