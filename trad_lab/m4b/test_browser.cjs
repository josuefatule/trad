// Exercise the actual injected observers with a deterministic event surface.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const packets=[],timers=[];
class Port {constructor(){this.listeners=[];}addEventListener(t,f){this.listeners.push(f);}start(){} dispatch(data){let stop=false;const e={data,stopImmediatePropagation(){stop=true;}};for(const f of this.listeners){f(e);if(stop)return;}this.onmessage?.(e);}}
class Socket {static OPEN=1;constructor(){this.listeners={};this.bufferedAmount=0;this.sent=[];}addEventListener(t,f){(this.listeners[t]??=[]).push(f);}send(x){this.sent.push(Buffer.from(x));}dispatch(m){for(const f of this.listeners.message||[])f({data:JSON.stringify(m)});}}
class Worker {constructor(){this.listeners=[];this.messages=[];}addEventListener(t,f){this.listeners.push(f);}postMessage(m){this.messages.push(m);}}
class AudioNode {constructor(){this.port=new Port();}}
const channels=[];
const c={location:{port:'18010',hostname:'127.0.0.1',href:'http://127.0.0.1:18010/capture',pathname:'/capture'},
  crypto:{randomUUID:()=> 'page'},performance:{timeOrigin:10000,now:()=>50},
  navigator:{mediaDevices:{getUserMedia:async()=>({getAudioTracks:()=>[{label:'Blue Yeti test double',getSettings:()=>({deviceId:'PRIVATE_ID',sampleRate:48000,channelCount:1})}]})}},
  BroadcastChannel:class{constructor(){channels.push(this);}postMessage(m){this.last=m;}},
  AudioWorkletNode:AudioNode,Worker,WebSocket:Socket,URL,Float32Array,Uint8Array,ArrayBuffer,
  btoa:s=>Buffer.from(s,'binary').toString('base64'),setInterval:f=>timers.push(f),
  __m4bBinding:s=>packets.push(JSON.parse(s)),document:{readyState:'loading',getElementById:()=>null,addEventListener:()=>{}},Date};
vm.createContext(c);vm.runInContext(fs.readFileSync('trad_lab/m4b/browser.js','utf8'),c);
const node=new c.AudioWorkletNode({sampleRate:48000,currentTime:1,getOutputTimestamp:()=>({contextTime:1,performanceTime:50})},'pcm-forwarder',{channelCount:1});
let received;node.port.onmessage=e=>received=e.data;
node.port.dispatch({m4b:true,frame:128,rate:48000,channels:1});assert.equal(received,undefined);
const input=Float32Array.of(.25,.5,-.5);node.port.dispatch(input);assert.equal(received,input);
const ws=new c.WebSocket('ws://127.0.0.1:18010/ws/session?token=DO_NOT_RECORD');
ws.dispatch({type:'config',session_id:'session',direction:{source_language:'en'},wlk:{session_language:'en',session_language_isolation:1,useAudioWorklet:true},control_token:'DO_NOT_RECORD'});
const pcm=Buffer.from([1,2,3,4]);ws.send(Uint8Array.from(pcm).buffer);ws.send(new ArrayBuffer(0));
for(const f of timers)f();assert.equal(packets.length,1);
const rows=packets[0].rows;assert.equal(rows.find(r=>r.kind==='pre').b64,Buffer.from(input.buffer).toString('base64'));
assert.equal(rows.find(r=>r.kind==='sent').b64,pcm.toString('base64'));
assert.equal(rows.filter(r=>r.kind==='sent').length,2);assert(rows.some(r=>r.kind==='binary_eof'));
assert(!JSON.stringify(packets).includes('DO_NOT_RECORD'));assert(!c.__m4bState().failed);
console.log('PASS: actual browser observers preserve PCM/metadata separation, WS bytes, EOF and omit credentials. Synthetic DOM paint remains untested.');
