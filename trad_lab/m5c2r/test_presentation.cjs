'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const copy=path.resolve(process.argv[2]),historical=path.resolve(process.argv[3]);
const {CaptionRenderer}=require(path.join(copy,'app/static/caption_renderer.js'));
const {geometry}=require(path.join(copy,'app/static/overlay_geometry.js'));
const config=JSON.parse(fs.readFileSync(path.join(historical,'latest_status.json'),'utf8')).status.caption_config;
config.mode='timed_queue';const geo=geometry(config,1920,1080);Object.assign(config,{max_lines:geo.maxLines,max_width:geo.maxWidth});
const captions=fs.readFileSync(path.join(historical,'overlay_wire.jsonl'),'utf8').trim().split(/\r?\n/).map(JSON.parse).filter(r=>r.message.type==='caption');
function rig(extra={}){
  let now=0,id=0;const timers=new Map(),shown=[],errors=[];
  const renderer=new CaptionRenderer({...config,...extra},{measure:(text,size)=>text.length*size*.57,now:()=>now,
    show:frame=>shown.push({...frame,at:now}),hide:()=>{},report:(reason,count)=>errors.push({reason,count}),
    schedule:(fn,ms)=>{timers.set(++id,{fn,at:now+ms});return id;},cancel:i=>timers.delete(i)});
  renderer.reset(captions[0].message.session_id);renderer.setState('live');
  const advance=end=>{while(true){const row=[...timers].sort((a,b)=>a[1].at-b[1].at)[0];if(!row||row[1].at>end)break;
    now=row[1].at;timers.delete(row[0]);row[1].fn();}now=end;};
  return {renderer,shown,errors,advance};
}
const clean=text=>text.replace(/\s+/gu,' ').trim();
const natural=rig();let maxPages=0;
for(const row of captions){natural.advance((row.perf_counter_ns-captions[0].perf_counter_ns)/1e6);natural.renderer.enqueue(row.message.caption);maxPages=Math.max(maxPages,natural.renderer.queue.length);}
natural.renderer.setState('stopped');natural.advance(300000);
assert.equal(natural.errors.length,0);assert.equal(natural.renderer.current,null);
for(const row of captions){const frames=natural.shown.filter(f=>f.caption.sequence===row.message.caption.sequence);
  assert.equal(clean(frames.map(f=>f.text).join(' ')),clean(row.message.caption.text));
  assert(frames.every(f=>f.text.split('\n').length<=geo.maxLines));}
assert.deepEqual(natural.shown.map(f=>f.caption.sequence),[...natural.shown].sort((a,b)=>a.caption.sequence-b.caption.sequence).map(f=>f.caption.sequence));
const bounded=rig({visual_queue_max:2,max_backlog_ms:4000});
for(const r of captions.slice(0,12))bounded.renderer.enqueue(r.message.caption);
assert(bounded.renderer.presentationFailed);assert.equal(bounded.renderer.queue.length,0);assert.equal(bounded.renderer.current,null);assert(bounded.errors.some(e=>e.reason==='queue_overflow'));
const previous=bounded.shown.length;bounded.renderer.enqueue(captions[20].message.caption);assert.equal(bounded.shown.length,previous);
bounded.renderer.clear();bounded.renderer.enqueue(captions[30].message.caption);assert.equal(bounded.shown.length,previous+1);
const cleared=rig();cleared.renderer.enqueue(captions[0].message.caption);cleared.renderer.clear();cleared.advance(10000);assert.equal(cleared.renderer.current,null);
cleared.renderer.enqueue(captions[1].message.caption);cleared.renderer.setState('disconnected');cleared.advance(20000);assert.equal(cleared.renderer.current,null);
const long=rig(),text=Array.from({length:40},(_,i)=>`palabra${i}`).join(' ');
long.renderer.enqueue({...captions[0].message.caption,text});long.renderer.setState('stopped');long.advance(120000);
assert(long.shown.length>1);assert.equal(clean(long.shown.map(f=>f.text).join(' ')),text);assert.equal(long.errors.length,0);
const result={status:'PASS',captions:captions.length,pages:natural.shown.length,words_shown_exact:true,display_drops:0,peak_queued_pages:maxPages,
  max_arrival_to_page_ms:Math.max(...natural.shown.map(f=>f.at-(captions.find(r=>r.message.caption.sequence===f.caption.sequence).perf_counter_ns-captions[0].perf_counter_ns)/1e6)),
  long_caption_pages:long.shown.length,long_caption_words_exact:true,
  stress:'bounded overflow hides publication and alerts; no silent queue truncation',scope:'Deterministic preserved B caption/timing replay, conservative synthetic text widths; no DeepL, ASR, OBS or TCP'};
if(process.argv[4])fs.writeFileSync(process.argv[4],JSON.stringify(result,null,2));console.log(JSON.stringify(result));
