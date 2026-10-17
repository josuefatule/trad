const {rig,caption}=require('../tests/caption_test_clock.cjs');
function compare(events){
  const result={};
  for(const mode of ['timed_queue','persistent_rolling']){
    const run=rig({mode,max_width:1500,max_lines:mode==='timed_queue'?2:3});
    for(let index=0;index<events.length;index++){
      run.advance(events[index].at_ms-run.now());
      run.enqueue(caption(events[index].text,index+1));
    }
    run.advance(120000);
    const delays=run.shown.map(s=>s.renderer_delay_ms).sort((a,b)=>a-b);
    result[mode]={submitted:events.length,shown_captions:new Set(run.shown.map(s=>s.caption.sequence)).size,
      rendered_blocks:run.shown.length,discarded_units:run.drops.reduce((n,d)=>n+d.count,0),
      drop_reasons:run.drops,maximum_queue_depth:run.maxQueue(),
      median_renderer_delay_ms:delays.length?(delays[Math.floor((delays.length-1)/2)]+delays[Math.ceil((delays.length-1)/2)])/2:null,
      max_renderer_delay_ms:delays.at(-1)??null};
  }
  return result;
}
module.exports={compare};
if(require.main===module){
  const fs=require('node:fs');
  const events=JSON.parse(fs.readFileSync(process.argv[2],'utf8').replace(/^\uFEFF/,''));
  console.log(JSON.stringify({real_ready_schedule:compare(events),
    rapid_400_ms:compare(events.map((e,i)=>({...e,at_ms:i*400})))},null,2));
}
