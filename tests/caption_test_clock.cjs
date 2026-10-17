const {CaptionRenderer} = require('../app/static/caption_renderer.js');
const defaults = {mode:'persistent_rolling',max_lines:3,font_size:48,max_width:600,stop_clear_ms:8000,
  min_display_ms:1800,max_display_ms:6500,reading_wps:3,visual_queue_max:64,max_backlog_ms:20000};
function rig(settings={}) {
  let now=0,id=0; const timers=new Map(), shown=[], drops=[];
  let maxQueue=0;
  const renderer=new CaptionRenderer({...defaults,...settings},{
    now:()=>now, measure:(text,size)=>text.length*size/4,
    show:frame=>{}, hide:()=>{}, rendered:sample=>shown.push({...sample,at:now}),
    report:(reason,count)=>drops.push({reason,count}),
    schedule:(fn,ms)=>{timers.set(++id,{fn,at:now+ms});return id;}, cancel:id=>timers.delete(id),
  });
  renderer.reset('a');renderer.setState('live');
  const advance=ms=>{
    const end=now+ms;
    while(true){
      const first=[...timers.entries()].sort((a,b)=>a[1].at-b[1].at)[0];
      if(!first||first[1].at>end)break;
      now=first[1].at;timers.delete(first[0]);first[1].fn();
    }
    now=end;
  };
  const enqueue=(caption)=>{renderer.enqueue(caption);maxQueue=Math.max(maxQueue,renderer.queue.length);};
  return {renderer,timers,shown,drops,advance,enqueue,now:()=>now,maxQueue:()=>maxQueue};
}
const caption=(text,sequence=1,session_id='a')=>({text,sequence,session_id,provider:'deepl'});
module.exports={rig,caption,defaults};
