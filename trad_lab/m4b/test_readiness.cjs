const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
async function check(readyState){
  const dcl=[],timers=[],packets=[],events={},start={disabled:true,addEventListener(){}};let nativeCalls=0,forwarded;
  const stream={getAudioTracks:()=>[]};
  class Node {constructor(){this.port={addEventListener(){},start(){}};}}
  const c={location:{port:'18010',hostname:'127.0.0.1',href:'http://127.0.0.1:18010/capture',pathname:'/capture'},
    crypto:{randomUUID:()=> 'page'},performance:{timeOrigin:1000,now:()=>10},
    navigator:{mediaDevices:{getUserMedia:async args=>{nativeCalls++;forwarded=args;return stream;}}},
    BroadcastChannel:class{postMessage(){}},AudioWorkletNode:Node,Worker:class{},WebSocket:class{},
    URL,Float32Array,Uint8Array,ArrayBuffer,Date,
    btoa:s=>Buffer.from(s,'binary').toString('base64'),setInterval:f=>timers.push(f),setTimeout,clearTimeout,
    __m4bBinding:s=>packets.push(JSON.parse(s)),MutationObserver:class{observe(){}},
    document:{readyState,getElementById:id=>id==='start'?start:null,addEventListener:(name,f)=>{if(name==='DOMContentLoaded')dcl.push(f);}},
    addEventListener:(name,f)=>events[name]=f};
  c.window=c;c.OperatorUI={render:()=>{start.disabled=false;}};
  vm.createContext(c);vm.runInContext(fs.readFileSync('trad_lab/m4b/guard.js','utf8'),c);
  vm.runInContext(fs.readFileSync('trad_lab/m4b/browser.js','utf8'),c);
  const firstMedia=c.navigator.mediaDevices.getUserMedia,firstGate=c.__m4bGate;
  vm.runInContext(fs.readFileSync('trad_lab/m4b/guard.js','utf8'),c);
  vm.runInContext(fs.readFileSync('trad_lab/m4b/browser.js','utf8'),c);
  assert.equal(c.navigator.mediaDevices.getUserMedia,firstMedia);assert.equal(c.__m4bGate,firstGate);
  let blocked=0;events.click({target:{closest:()=>start},preventDefault:()=>blocked++,stopImmediatePropagation:()=>blocked++});
  assert.equal(blocked,2);assert.equal(start.disabled,true);
  const constraints={audio:{deviceId:{exact:'unchanged-device'}}};
  const pending=c.navigator.mediaDevices.getUserMedia(constraints);assert.equal(nativeCalls,0);
  assert.throws(()=>c.__m4bGate.approve('page'));
  for(const f of dcl)f();for(const f of timers)f();
  assert.equal(c.__m4bState().ready_acknowledged,false);
  c.__m4bAck(packets[0].id);assert.equal(c.__m4bState().ready_acknowledged,true);
  assert.throws(()=>c.__m4bGate.approve('stale-page'));
  c.__m4bGate.approve('page');assert.equal(start.disabled,false);
  assert.equal(await pending,stream);assert.equal(nativeCalls,1);assert.equal(forwarded,constraints);
  c.__m4bGate.fail('test-failure');assert.equal(start.disabled,true);
  await assert.rejects(c.navigator.mediaDevices.getUserMedia(constraints));assert.equal(nativeCalls,1);
  assert.throws(()=>c.__m4bGate.approve('page'));
}
(async()=>{
  await check('loading');await check('complete');
  console.log('PASS: early/late DOM installation and idempotence; START blocked until observer/writer ACK; stale/failure rejected; native microphone constraints and return unchanged when prepared. No real audio.');
})().catch(e=>{console.error(e);process.exitCode=1;});
