'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const {PCMQueue}=require('./physical_core.cjs'),{FIRResampler,s16}=require('./resampler.cjs');
let checks=0;
for(const rate of [16000,44100,48000]){
  const x=Float32Array.from({length:rate},(_,i)=>.4*Math.sin(2*Math.PI*997*i/rate));
  function run(size){const r=new FIRResampler(rate),out=[];for(let i=0;i<x.length;i+=size)out.push(...r.push(x.slice(i,i+size)));out.push(...r.finish());assert.throws(()=>r.finish());return Float32Array.from(out);}
  const whole=run(60000);
  for(const size of [1,127,128,2048,4093]){assert.deepEqual(run(size),whole);checks++;}
  assert.equal(whole.length,16000);assert.equal(new FIRResampler(rate).finish().length,0);checks+=2;
}
assert.throws(()=>new FIRResampler(22050));assert.throws(()=>new FIRResampler(48000).push(Float32Array.of(NaN)));checks+=2;
const identity=new FIRResampler(16000),input=Float32Array.of(-1,0,1,.5);assert.deepEqual(new Int16Array(s16(identity.push(input))),Int16Array.of(-32768,0,32767,16383));checks++;
const original=Buffer.alloc(140002);for(let i=0;i<original.length;i++)original[i]=i%251;
// Use standalone ArrayBuffers to avoid Node's pooled-buffer backing storage.
const queue=new PCMQueue();for(let at=0;at<original.length;at+=4096)queue.append(Uint8Array.from(original.subarray(at,at+4096)).buffer);
queue.flush();let blocks=[];
while(true){const b=queue.take();if(!b)break;assert.equal(queue.take(),null);blocks.push(Buffer.from(b));queue.hash('test');queue.credit({...queue.pending});}
assert.deepEqual(Buffer.concat(blocks),original);assert.equal(queue.acked,original.length);assert.equal(queue.bytes,0);assert(queue.finish());assert(!queue.finish());checks+=6;
const slow=new PCMQueue(64000);slow.append(new ArrayBuffer(64000));slow.take();assert.throws(()=>slow.append(new ArrayBuffer(2)));assert(!slow.finish());checks+=2;
const bad=new PCMQueue();bad.append(new ArrayBuffer(64000));bad.take();bad.hash('a');assert.throws(()=>bad.credit({...bad.pending,sha256:'b'}));assert(!bad.finish());checks+=2;
let Processor;
const messages=[];const context={Float32Array,sampleRate:48000,AudioWorkletProcessor:class{constructor(){this.port={postMessage:m=>messages.push(m)};}},registerProcessor:(name,c)=>Processor=c};
vm.runInNewContext(fs.readFileSync(__dirname+'/worklet.js','utf8'),context);
const worklet=new Processor();for(let i=0;i<16;i++)worklet.process([[new Float32Array(128)]]);
assert.equal(messages[0].samples,2048);assert.equal(messages[0].channels,1);assert.equal(messages[0].first_sample,0);
worklet.port.onmessage({data:{command:'ack',sequence:0}});worklet.process([[new Float32Array(128)]]);worklet.port.onmessage({data:{command:'flush'}});
assert.equal(messages.at(-1).input_samples,2176);assert.equal(messages.at(-1).incomplete,false);checks+=5;
const blocked=new Processor();for(let i=0;i<16*9;i++)blocked.process([[new Float32Array(128)]]);assert(blocked.failed);assert(messages.some(m=>m.error==='worklet_backlog_exhausted'));checks+=2;
// The real worker receives the actual worklet batches and preserves own sample counter.
const workerMessages=[];const w={Float32Array,ArrayBuffer,M5CFIR:{FIRResampler,s16},importScripts:()=>{},postMessage:m=>workerMessages.push(m)};
vm.runInNewContext(fs.readFileSync(__dirname+'/resample_worker.js','utf8'),w);
w.onmessage({data:{command:'init',sample_rate:48000}});
const batch=messages[0];w.onmessage({data:{command:'record',...batch}});
w.onmessage({data:{command:'flush',input_samples:2048,batches:1}});
assert(workerMessages.at(-1).flushed);assert.equal(workerMessages.reduce((n,m)=>n+(m.buffer?.byteLength||0),0),Math.ceil(2048/3)*2);checks+=2;
console.log(JSON.stringify({status:'PASS',checks,scope:'Actual DSP/worklet/worker/credit-queue under deterministic doubles; no native microphone'}));
