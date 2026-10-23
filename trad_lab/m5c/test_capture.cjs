/* Execute the real prepared page+worker glue with synthetic APIs only. */
'use strict';
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict'),{webcrypto}=require('node:crypto');
const {PCMQueue}=require('./physical_core.cjs'),dsp=require('./resampler.cjs');
const tick=()=>new Promise(r=>setImmediate(r));
async function until(fn){for(let i=0;i<400;i++){if(fn())return;await new Promise(r=>setTimeout(r,5));}throw Error('Synthetic page did not progress within 2 s');}
async function rig(enabled){
  let micCalls=0,sockets=[],node=null,stopped=false;
  const items=Object.fromEntries(['status','start','stop'].map(k=>[k,{disabled:false,textContent:''}]));
  const handlers={},owner={postMessage:()=>{}},sent=[],acks=[];
  class FakeSocket{
    static OPEN=1;
    constructor(url,protocol){this.readyState=1;this.bufferedAmount=0;sockets.push(this);this.bytes=0;this.seq=0;}
    send(b){
      sent.push(Buffer.from(b));
      if(b.byteLength){
        const bytes=b.byteLength,sha=require('node:crypto').createHash('sha256').update(Buffer.from(b)).digest('hex');this.bytes+=bytes;
        const ack={protocol_version:1,type:'pcm_ack',session_id:'test',frame_sequence:this.seq++,bytes,received_bytes:this.bytes,sha256:sha};acks.push(ack);setImmediate(()=>this.onmessage({data:JSON.stringify(ack)}));
      }else{
        setImmediate(async()=>{await this.onmessage({data:JSON.stringify({protocol_version:1,type:'asr',payload:{type:'ready_to_stop'}})});
          await this.onmessage({data:JSON.stringify({protocol_version:1,type:'status',state:'stopped',completion:'complete',experimental_asr:{}})});this.onclose();});
      }
    }
    close(){this.readyState=3;}
  }
  class FakeContext{
    constructor(){this.sampleRate=48000;this.audioWorklet={addModule:async()=>{}};}
    createMediaStreamSource(){return {connect:()=>{},disconnect:()=>{}};}
    async resume(){}async close(){}
  }
  class FakeNode{
    constructor(){node=this;this.samples=0;this.batches=0;this.port={postMessage:m=>{
      if(m.command==='flush')this.port.onmessage({data:{flushed:true,input_samples:this.samples,batches:this.batches,incomplete:false}});
    }};}
    disconnect(){}
    feed(x){const m={sequence:this.batches++,first_sample:this.samples,samples:x.length,channels:1,sample_rate:48000,buffer:x.buffer};this.samples+=x.length;this.port.onmessage({data:m});}
  }
  class FakeWorker{
    constructor(){const worker=this;this.ctx={Float32Array,ArrayBuffer,M5CFIR:dsp,importScripts:()=>{},postMessage:m=>worker.onmessage({data:m})};vm.runInNewContext(fs.readFileSync(__dirname+'/resample_worker.js','utf8'),this.ctx);}
    postMessage(m){this.ctx.onmessage({data:m});}terminate(){}
  }
  const context={console,Float32Array,ArrayBuffer,Uint8Array,setTimeout,clearTimeout,crypto:webcrypto,M5CPhysical:{PCMQueue},
    document:{getElementById:k=>items[k]},location:{origin:'http://127.0.0.1:18010',protocol:'http:',host:'127.0.0.1:18010'},opener:owner,
    addEventListener:(k,f)=>handlers[k]=f,fetch:async url=>({ok:true,json:async()=>({physical_enabled:enabled})}),
    navigator:{mediaDevices:{getUserMedia:async()=>{micCalls++;return {getAudioTracks:()=>[{label:'Yeti',getSettings:()=>({deviceId:'device'})}],getTracks:()=>[{stop:()=>{stopped=true;}}]};}}},
    WebSocket:FakeSocket,AudioContext:FakeContext,AudioWorkletNode:FakeNode,Worker:FakeWorker};
  vm.runInNewContext(fs.readFileSync(__dirname+'/physical_capture.js','utf8'),context);await tick();await tick();
  handlers.message({origin:context.location.origin,source:owner,data:{type:'capture_start',token:'fake-owner',deviceId:'device',direction:'en-es'}});
  return {items,sent,acks,get node(){return node;},get micCalls(){return micCalls;},sockets,start:()=>items.start.onclick(),stop:()=>items.stop.onclick(),get stopped(){return stopped;}};
}
(async()=>{
  const disabled=await rig(false);assert(disabled.items.start.disabled);await disabled.start();assert.equal(disabled.micCalls,0);assert.equal(disabled.sockets.length,0);
  const live=await rig(true);await live.start();const socket=live.sockets[0];
  await socket.onmessage({data:JSON.stringify({protocol_version:1,type:'config',session_id:'test',wlk:{session_language:'en',session_language_isolation:1},experimental_transport:{pcm_credit:1,frame_bytes:64000,credit_seconds:39}})});
  const input=Float32Array.from({length:100352},(_,i)=>.2*Math.sin(2*Math.PI*1000*i/48000));
  for(let at=0;at<input.length;at+=2048)live.node.feed(input.slice(at,at+2048));
  await until(()=>live.sent.length||live.items.status.textContent.startsWith('INCOMPLETE'));
  assert(!live.items.status.textContent.startsWith('INCOMPLETE'),live.items.status.textContent);
  live.stop();await until(()=>live.sent.some(b=>!b.length)||live.items.status.textContent.startsWith('INCOMPLETE'));await tick();await tick();
  assert(!live.items.status.textContent.startsWith('INCOMPLETE'),live.items.status.textContent);
  const r=new dsp.FIRResampler(48000),expected=Buffer.concat([Buffer.from(dsp.s16(r.push(input.slice(0,60000)))),Buffer.from(dsp.s16(r.push(input.slice(60000)))),Buffer.from(dsp.s16(r.finish()))]);
  assert(Buffer.concat(live.sent.filter(b=>b.length)).equals(expected),'Physical glue PCM differs');assert.equal(live.sent.filter(b=>!b.length).length,1);
  assert.equal(live.acks.length,2);assert(live.stopped);assert.equal(JSON.parse(live.items.status.textContent).terminal,true);
  const early=await rig(true);await early.start();early.stop();
  await early.sockets[0].onmessage({data:JSON.stringify({protocol_version:1,type:'config',session_id:'test',wlk:{session_language:'en',session_language_isolation:1},experimental_transport:{pcm_credit:1,frame_bytes:64000,credit_seconds:39}})});
  for(let i=0;i<5;i++)await tick();assert.equal(early.sent.length,1);assert.equal(early.sent[0].length,0);assert.equal(early.node,null);
  console.log(JSON.stringify({status:'PASS',checks:12,scope:'Real page and worker with synthetic WebAudio/media/socket; C1 native API calls zero. No physical or TCP claim.'}));
})().catch(e=>{console.error(e);process.exitCode=1;});
