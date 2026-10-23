/* Actual repaired page and FIR worker, synthetic native APIs. */
'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert/strict'),{webcrypto}=require('crypto');
const copy=path.resolve(process.argv[2]),base=path.join(copy,'app/static');
const {PCMQueue}=require(path.join(copy,'trad_lab/m5c/physical_core.cjs')),dsp=require(path.join(copy,'trad_lab/m5c/resampler.cjs'));
const tick=()=>new Promise(r=>setImmediate(r));
async function until(f){for(let i=0;i<400;i++){if(f())return;await new Promise(r=>setTimeout(r,5));}throw Error('Synthetic page did not finish within 2 s');}
async function rig(injectFailure){
  let node,socket,traceFailed=false,micStopped=false,eofs=0;const sent=[],handlers={};
  const items=Object.fromEntries(['status','start','stop','level'].map(n=>[n,{disabled:false,textContent:''}]));
  const trace={record:()=>true,start:()=>true,binary:()=>{
    if(injectFailure&&!traceFailed){traceFailed=true;queueMicrotask(()=>context.M5C2_EVIDENCE_FAILURE(Error('injected_evidence_failure')));return false;}return !traceFailed;
  },finish:async failed=>({evidence_complete:true,capture_failed:failed||traceFailed})};
  class Socket{
    static OPEN=1;
    constructor(){socket=this;this.readyState=1;this.bufferedAmount=0;this.sequence=0;this.bytes=0;}
    send(buffer){sent.push(Buffer.from(buffer));
      if(buffer.byteLength){this.bytes+=buffer.byteLength;const m={protocol_version:1,type:'pcm_ack',session_id:'test',frame_sequence:this.sequence++,bytes:buffer.byteLength,received_bytes:this.bytes,sha256:require('crypto').createHash('sha256').update(Buffer.from(buffer)).digest('hex')};queueMicrotask(()=>this.onmessage({data:JSON.stringify(m)}));}
      else{eofs++;queueMicrotask(async()=>{await this.onmessage({data:JSON.stringify({protocol_version:1,type:'asr',payload:{type:'ready_to_stop'}})});await this.onmessage({data:JSON.stringify({protocol_version:1,type:'status',state:'stopped',completion:'complete'})});});}}
    close(){this.readyState=3;}
  }
  class Context{constructor(){this.sampleRate=48000;this.audioWorklet={addModule:async()=>{}};}createMediaStreamSource(){return {connect(){},disconnect(){}};}async resume(){}async close(){}}
  class Node{constructor(){node=this;this.batches=0;this.samples=0;this.port={postMessage:m=>{if(m.command==='flush')queueMicrotask(()=>this.port.onmessage({data:{flushed:true,input_samples:this.samples,batches:this.batches,incomplete:false}}));}};}
    feed(buffer){this.port.onmessage({data:{sequence:this.batches++,first_sample:this.samples,samples:buffer.length,channels:1,sample_rate:48000,buffer:buffer.buffer}});this.samples+=buffer.length;}disconnect(){}}
  class Worker{constructor(){this.ctx={Float32Array,ArrayBuffer,M5CFIR:dsp,importScripts(){},postMessage:m=>this.onmessage({data:m})};vm.runInNewContext(fs.readFileSync(base+'/m5c_worker.js','utf8'),this.ctx);}postMessage(m){this.ctx.onmessage({data:m});}terminate(){}}
  const owner={postMessage(){}};
  const context={console,Float32Array,ArrayBuffer,Uint8Array,setTimeout,clearTimeout,queueMicrotask,crypto:webcrypto,
    document:{getElementById:n=>items[n]},location:{origin:'http://127.0.0.1:18010',protocol:'http:',host:'127.0.0.1:18010'},opener:owner,
    M5CPhysical:{PCMQueue},M5C2Trace:trace,addEventListener:(n,f)=>handlers[n]=f,
    fetch:async()=>({ok:true,json:async()=>({physical_enabled:true})}),
    navigator:{mediaDevices:{getUserMedia:async()=>({getAudioTracks:()=>[{label:'Yeti',getSettings:()=>({deviceId:'test-device'})}],getTracks:()=>[{stop:()=>micStopped=true}]})}},
    AudioContext:Context,AudioWorkletNode:Node,Worker,WebSocket:Socket};
  vm.runInNewContext(fs.readFileSync(base+'/m5c_capture.js','utf8'),context);await tick();
  handlers.message({source:owner,origin:context.location.origin,data:{type:'capture_start',token:'test-owner',deviceId:'test-device',direction:'en-es'}});
  await items.start.onclick();await socket.onmessage({data:JSON.stringify({protocol_version:1,type:'config',session_id:'test',wlk:{session_language:'en',session_language_isolation:1},experimental_transport:{pcm_credit:1,frame_bytes:64000,credit_seconds:39}})});
  const input=Float32Array.from({length:2048},(_,i)=>.2*Math.sin(2*Math.PI*997*i/48000));
  assert.doesNotThrow(()=>node.feed(input));
  if(!injectFailure)items.stop.onclick();
  await until(()=>items.status.textContent.startsWith('{')&&JSON.parse(items.status.textContent).evidence);
  const result=JSON.parse(items.status.textContent),fir=new dsp.FIRResampler(48000);
  const expected=Buffer.concat([Buffer.from(dsp.s16(fir.push(input))),Buffer.from(dsp.s16(fir.finish()))]);
  assert(Buffer.concat(sent).equals(expected));assert.equal(eofs,1);assert(micStopped);assert(result.terminal);
  assert.equal(result.experiment_complete,!injectFailure);assert.equal(result.evidence.capture_failed,!!injectFailure);
}
(async()=>{await rig(false);await rig(true);console.log(JSON.stringify({status:'PASS',checks:14,scope:'Real repaired capture/FIR/queue; normal STOP and recorder failure both drain exact PCM, single EOF, credits, terminal; recorder failure never reported experiment complete; native APIs synthetic'}));})().catch(e=>{console.error(e);process.exitCode=1;});
