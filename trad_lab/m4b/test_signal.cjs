'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const {ContinuousBox,s16}=require('./resampler.cjs');
// Independent area-overlap oracle, recomputed from absolute sample positions.
function oracle(x,rate){
  const result=[];
  for(let j=0;j<Math.ceil(x.length*16000/rate);j++) {
    const start=j*rate,end=Math.min((j+1)*rate,x.length*16000);let sum=0;
    for(let i=Math.floor(start/16000);i<Math.ceil(end/16000);i++)sum+=x[i]*Math.max(0,Math.min(end,(i+1)*16000)-Math.max(start,i*16000));
    result.push(sum/(end-start));
  }
  return Float32Array.from(result);
}
function convert(x,rate,parts){const b=new ContinuousBox(rate),out=[];let k=0,i=0;while(i<x.length){const n=parts[k++%parts.length];out.push(b.push(x.subarray(i,i+n)));i+=n;}const end=b.finish();out.push(end.tail);assert.throws(()=>b.finish());assert.throws(()=>b.push(x));return {pcm:Buffer.concat(out.map(s16)),end};}
let cases=0;const evidence=[];
for(const rate of [16000,44100,48000]) {
  // Ramps/impulses + incommensurate tones identify order and phase changes.
  for(const n of [0,1,2,3,127,128,129,1001,rate+17]) {
    const x=Float32Array.from({length:n},(_,i)=>.3*Math.sin(i*.071)+.1*Math.cos(i*.013)+(i===127?.4:0));
    const expected=s16(oracle(x,rate));
    for(const parts of [[1],[128],[480],[960],[1,7,127,511,3,128],[4096]]) {
      const r=convert(x,rate,parts);assert.deepEqual(r.pcm,expected);assert.equal(r.end.outputs,Math.ceil(n*16000/rate));cases++;
    }
  }
  for(const parts of [[128],[480],[1,127,960]]) {
    const x=new Float32Array(rate*60).fill(.25),r=convert(x,rate,parts);
    assert.equal(r.end.outputs,960000);assert.equal(r.end.coverage,0);cases++;
  }
  const original=[];const ctx={self:{postMessage:m=>{if(m.buffer)original.push(m.buffer.byteLength/2);}},Float32Array,ArrayBuffer,DataView,Math};
  vm.createContext(ctx);vm.runInContext(fs.readFileSync('app/static/recorder_worker.js','utf8'),ctx);
  ctx.self.onmessage({data:{command:'init',config:{sampleRate:rate,targetSampleRate:16000}}});
  let left=rate*60;while(left){const n=Math.min(128,left);ctx.self.onmessage({data:{command:'record',buffer:new Float32Array(n).buffer}});left-=n;}
  evidence.push({rate,input_seconds:60,block:128,original_samples:original.reduce((a,b)=>a+b,0),candidate_samples:960000});
}
assert.throws(()=>new ContinuousBox(32000));
assert.throws(()=>new ContinuousBox(48000).push(Float32Array.of(NaN)));
// The worklet metadata never changes the original sample or flush messages.
let Processor;const messages=[];
const context={AudioWorkletProcessor:class{constructor(){this.port={postMessage:(m)=>messages.push(m)};}},
  registerProcessor:(n,p)=>Processor=p,currentFrame:0,sampleRate:48000,Float32Array};
vm.createContext(context);
const src=fs.readFileSync('app/static/pcm_worklet.js','utf8');
const modified=src.replace('      const channelData = input[0];','      this.port.postMessage({m4b:true,frame:currentFrame,rate:sampleRate,channels:input.length});\n      const channelData = input[0];');
vm.runInContext(modified,context);const processor=new Processor();const input=Float32Array.of(.1,.2,.3);
processor.process([[input]]);assert.equal(messages[0].m4b,true);assert.deepEqual(messages[1],input);
processor.port.onmessage({data:{flush:true}});processor.process([[input]]);assert.equal(messages.length,3);assert.equal(messages[2].flushed,true);
console.log(JSON.stringify({status:'PASS',partition_cases:cases,worklet_sample_and_eof_preserved:true,evidence},null,2));
