'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),crypto=require('crypto');
const source=fs.readFileSync(__dirname+'/evidence.js','utf8');
const tick=()=>new Promise(r=>setImmediate(r));
async function rig(mode='ok'){
  let clock=0,id=0,calls=0,finals=0,total=0,notifications=0,token='owner-1',resolve;
  const timers=new Map(),intervals=new Map(),received=crypto.createHash('sha256');
  const context={TextEncoder,Uint8Array,AbortController,performance:{now:()=>clock,timeOrigin:1000},opener:{},queueMicrotask,
    btoa:s=>Buffer.from(s,'binary').toString('base64'),
    M5C2_EVIDENCE_FAILURE:()=>{notifications++;},
    setInterval:fn=>{intervals.set(++id,fn);return id;},clearInterval:i=>intervals.delete(i),
    setTimeout:(fn,ms)=>{timers.set(++id,{fn,ms});return id;},clearTimeout:i=>timers.delete(i),
    fetch:async(url,options)=>{
      calls++;assert.equal(url,'/api/m5c2/evidence');assert.equal(options.headers['x-operator-token'],token);
      const m=JSON.parse(options.body);assert.equal(m.sequence,calls-1);assert.equal(m.session_id,'s');
      if(mode==='slow'&&calls===1)await new Promise(r=>resolve=r);
      if(mode==='timeout')await new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(Object.assign(Error(),{name:'AbortError'}))));
      if(mode==='http')return {ok:false};
      for(const row of m.rows)if(row.b64!==undefined)received.update(Buffer.from(row.b64,'base64'));
      total+=Buffer.byteLength(JSON.stringify(m.rows));if(m.final)finals++;
      return {ok:true,json:async()=>({sequence:mode==='bad_ack'?99:m.sequence,written:true,final:m.final,writer_json_bytes:mode==='soft_limit'?128*1024*1024:total})};
    }};
  vm.runInNewContext(source,context);const t=context.M5C2Trace;t.start('s',()=>token);await tick();
  return {t,context,pulse:async()=>{clock+=50;for(const [key,entry] of [...timers])if(entry.ms===50){timers.delete(key);entry.fn();}for(const fn of intervals.values())fn();await tick();},
    timeout:()=>{for(const entry of [...timers.values()])if(entry.ms===5000)entry.fn();},
    unblock:()=>resolve?.(),rotate:()=>token='owner-2',pauseOwner:()=>token='',get calls(){return calls;},get finals(){return finals;},
    get total(){return total;},get notifications(){return notifications;},digest:()=>received.digest('hex')};
}
(async()=>{
  let checks=0;
  const live=await rig(),expected=crypto.createHash('sha256');
  for(let index=0;index<7000;index++){
    const bytes=Buffer.alloc(8192);bytes.writeUInt32LE(index);expected.update(bytes);
    assert(live.t.binary('pre',Uint8Array.from(bytes).buffer,{sequence:index,samples:2048,channels:1,sample_rate:48000}));
    if(index%12===11)await live.pulse();
  }
  live.rotate();await live.pulse();live.t.record({kind:'terminal',result:{transport:'complete'}});
  const result=await live.t.finish();assert(result.evidence_complete&&!result.capture_failed);
  assert(live.total>64*1024*1024);assert(result.peak_queue_bytes<8*1024*1024);
  assert.equal(live.digest(),expected.digest('hex'));assert.equal(result.queued_bytes,0);assert.equal(live.finals,1);
  assert.strictEqual(live.t.finish(),live.t.finish());checks+=8;
  const slow=await rig('slow');slow.t.binary('pre',new ArrayBuffer(8192));await slow.pulse();
  for(let i=0;i<1000;i++)assert.doesNotThrow(()=>slow.t.binary('pre',new ArrayBuffer(8192)));
  await tick();assert(slow.t.stats().failed);assert(slow.t.stats().queued_bytes<=8*1024*1024);
  assert.equal(slow.notifications,1);slow.unblock();await tick();const stopped=await slow.t.finish();
  assert(stopped.evidence_complete&&stopped.capture_failed);assert.equal(slow.finals,1);checks+=5;
  for(const mode of ['http','bad_ack','timeout']){
    const r=await rig(mode);r.t.record({kind:'clock'});await r.pulse();
    if(mode==='timeout'){r.timeout();await tick();}
    const failed=await r.t.finish();assert(!failed.evidence_complete&&failed.capture_failed);
    assert.equal(r.calls,1);assert.equal(r.notifications,1);assert(failed.queued_bytes>0);checks+=4;
  }
  const limit=await rig('soft_limit');limit.t.record({kind:'clock'});await limit.pulse();
  assert.equal(limit.t.stats().reason,'evidence_session_budget_stop');
  const final=await limit.t.finish();assert(final.evidence_complete&&final.capture_failed);checks+=2;
  const reload=await rig();reload.pauseOwner();reload.t.record({kind:'clock'});
  for(let i=0;i<5;i++)await reload.pulse();assert.equal(reload.calls,0);assert(!reload.t.stats().failed);
  reload.rotate();await reload.pulse();const resumed=await reload.t.finish();
  assert(resumed.evidence_complete&&!resumed.capture_failed);checks+=3;
  console.log(JSON.stringify({status:'PASS',checks,scope:'VM recorder, >64 MiB cumulative exact bytes, <8 MiB queue, slow HTTP, timeout, bad ACK, no retry, rotating owner, graceful failure seal'}));
})().catch(e=>{console.error(e);process.exitCode=1;});
