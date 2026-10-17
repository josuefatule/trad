const assert=require('node:assert/strict');
const {rig,caption}=require('./caption_test_clock.cjs');
const {OverlayClock}=require('../app/static/overlay_latency.js');

const pause=rig();pause.enqueue(caption('This caption stays visible.'));
pause.advance(3600000);
assert.match(pause.renderer.current.text,/stays visible/);
assert.equal(pause.timers.size,0);
pause.enqueue(caption('New content arrives immediately.',2));
assert.equal(pause.shown.at(-1).renderer_delay_ms,0);
assert.match(pause.renderer.current.text,/visible\. New content/);
assert.equal(pause.renderer.queue.length,0);
pause.renderer.setState('stopped');pause.advance(7999);assert(pause.renderer.current);
pause.advance(1);assert.equal(pause.renderer.current,null);

for(const lines of [2,3]){
  const rolling=rig({max_lines:lines,max_width:240});
  for(let index=1;index<=12;index++) rolling.enqueue(caption(`Caption ${index} arrives.`,index));
  assert(rolling.renderer.current.text.split('\n').length<=lines);
  assert.match(rolling.renderer.current.text,/12 arrives\./);
  assert.doesNotMatch(rolling.renderer.current.text,/Caption 1 /);
  assert.equal(rolling.shown.length,12);
  assert(rolling.shown.every(s=>s.renderer_delay_ms===0&&s.visual_queue_depth===0));
  assert(rolling.shown.at(-1).rolled_out_lines>0);
}
const reset=rig();reset.enqueue(caption('Old session'));
reset.renderer.reset('b');reset.advance(10000);assert.equal(reset.renderer.current,null);
reset.enqueue(caption('stale',2));assert.equal(reset.renderer.current,null);
reset.enqueue(caption('Current.',1,'b'));reset.enqueue(caption('DUPLICATE',1,'b'));
assert.equal(reset.renderer.current.text,'Current.');
reset.renderer.setState('disconnected');assert.equal(reset.renderer.current,null);
reset.renderer.restore([caption('Current.',1,'b')]);reset.renderer.setState('live');
assert.equal(reset.renderer.current.text,'Current.');
reset.enqueue(caption('DUPLICATE',1,'b'));assert.equal(reset.renderer.current.text,'Current.');
reset.enqueue(caption('Next.',2,'b'));assert.equal(reset.renderer.current.text,'Current. Next.');
reset.renderer.configure({...reset.renderer.config,max_lines:2,max_width:240});
assert(reset.renderer.current.text.split('\n').length<=2);
reset.renderer.setState('stopped',500);reset.advance(500);assert.equal(reset.renderer.current,null);

const long=rig({max_width:240});
long.enqueue(caption(Array.from({length:100},(_,i)=>`word${i}`).join(' ')));
assert(long.renderer.current.text.split('\n').length<=3);
assert.match(long.renderer.current.text,/word99/);
assert(long.drops.some(d=>d.reason==='rolling_overflow'));
assert.equal(long.renderer.queue.length,0);
long.advance(100000);assert(long.renderer.current);
const punctuation=rig();punctuation.enqueue(caption('Hello,'));punctuation.enqueue(caption('world! Café.',2));
assert.equal(punctuation.renderer.current.text,'Hello, world! Café.');

// Known independent clocks with 10 ms symmetric delivery and 2 ms server processing.
const clock=new OverlayClock();
assert.deepEqual(clock.estimate({},1,2),{});
clock.synchronize({client_sent_ms:100,server_received_mono_ms:10110,server_sent_mono_ms:10112},122);
const estimates=clock.estimate({published_mono_ms:10200,latency:{ready_to_hub_ms:900,asr_to_hub_ms:4400}},210,240);
assert.equal(estimates.hub_delivery_estimate_ms,10);
assert.equal(estimates.delivery_uncertainty_ms,10);
assert.equal(estimates.ready_to_visible_estimate_ms,940);
const coarseClock=new OverlayClock();
coarseClock.synchronize({client_sent_ms:100,server_received_mono_ms:10110,
  server_sent_mono_ms:10112,server_clock_resolution_ms:15.625},122);
assert.equal(coarseClock.estimate({published_mono_ms:10200},210,240).delivery_uncertainty_ms,25.625);
assert.deepEqual(clock.estimate({},210,240,true),{});
assert.deepEqual(clock.estimate({},40000,40030),{});
console.log('PASS: persistent rolling, immediate arrivals, pauses, lifecycle, snapshots and clock estimates');
module.exports=true;
