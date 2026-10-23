const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {actions,stats,userError}=require('../app/static/operator_console.js');
for(const phase of ['STARTING','STOPPING']) {
  assert.deepEqual(actions(phase,{authorized:true,canStart:true,ownsSession:true,hasSession:true,localActive:true}),{start:false,stop:false,clear:false});
}
assert(actions('IDLE',{authorized:true,canStart:true}).start);
assert(actions('LIVE',{authorized:true,localActive:true,ownsSession:true,hasSession:true}).stop);
assert(!actions('LIVE',{authorized:true,hasSession:true}).clear);
assert.equal(stats([undefined,null,NaN,1],3),null);
assert.deepEqual(stats([1,2,3,4,5],5),{count:5,median:3,p95:5});
assert.match(userError({name:'NotAllowedError'}),/denegado/);
assert.match(userError('HTTP Error 403: PRIVATE'),/autenticación/);
assert.doesNotMatch(userError('HTTP Error 403: PRIVATE'),/PRIVATE/);

async function rig({old=false,microphoneError=null,bidirectional=false}={}) {
  let now=0;
  const nodes=new Map(),sockets=[],sent=[],requests=[];
  const get=id=>{
    if(!nodes.has(id))nodes.set(id,{textContent:'',value:'',dataset:{},scrollHeight:300,clientHeight:100,scrollTop:200,
      replaceChildren(){},set innerHTML(value){throw Error('Unsafe HTML');}});
    return nodes.get(id);
  };
  const status={protocol_version:1,session_id:null,state:'waiting',can_start:true,owns_session:false,
    can_change_direction:true,session_open:false,
    overlay_connections:0,sequence:0,visual_generation:0,caption_config:{mode:'persistent_rolling',max_lines:3},
    translator:{provider:'deepl',state:'ready'},latency_diagnostics:{backend_samples:[],observers:[],translation_queue_depth:0}};
  const diagnostic={minimum_samples:5,poll_seconds:2,sustained_seconds:6,queue_depth_warning:3,queue_delay_warning_ms:1000,render_warning_ms:500};
  class Socket {
    static OPEN=1;
    constructor(url,protocols){this.url=url;this.readyState=1;this.bufferedAmount=0;this.protocols=protocols;sockets.push(this);}
    send(data){sent.push(data);}
    close(){this.readyState=3;this.onclose?.();}
  }
  class Worklet {
    constructor(){this.port={postMessage:message=>{if(message.command==='flush')this.port.onmessage({data:{flushed:true}});}};}
    disconnect(){}
  }
  class Worker {
    postMessage(message){if(message.command==='flush')this.onmessage({data:{flushed:true}});}
    terminate(){}
  }
  const track={label:'Blue Yeti test fixture',stop(){}};
  const context=vm.createContext({document:{getElementById:get},window:{addEventListener(){}},
    location:{protocol:'http:',host:'localhost:8010',search:''},URLSearchParams,
    Date:class extends Date {static now(){return now;}},setTimeout(){},clearTimeout(){},Option:class{},
    navigator:{mediaDevices:{enumerateDevices:async()=>[],getUserMedia:async()=>{
      if(microphoneError)throw microphoneError;
      return {getAudioTracks:()=>[track],getTracks:()=>[track]};
    }}},
    AudioContext:class {constructor(){this.state='running';this.sampleRate=48000;this.audioWorklet={addModule:async()=>{}};}
      async resume(){} async close(){this.state='closed';} createMediaStreamSource(){return {connect(){},disconnect(){}};}},
    AudioWorkletNode:Worklet,Worker,WebSocket:Socket,
    fetch:async(url,options={})=>{
      requests.push({url,options});
      if(url.includes('bootstrap'))return {ok:!old,json:async()=>({protocol_version:1,capabilities:{operator_console:1,captions_clear:1,...(bidirectional?{session_direction:1}:{})},default_direction:'en-es',control_token:'private-control',diagnostics_config:diagnostic})};
      if(url.includes('/clear')){status.visual_generation++;return {ok:true,json:async()=>({protocol_version:1,applied:true})};}
      return {ok:true,json:async()=>structuredClone(status)};
    },
  });
  for(const file of ['operator_console.js','operator.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/',file),'utf8'),context);
    if(file==='operator_console.js')context.OperatorConsole=context.window.OperatorConsole;
  }
  await context.OperatorUI.ready;
  return {get,context,status,sockets,sent,requests,advance:ms=>{now+=ms;},
    send:async data=>sockets.at(-1).onmessage({data:JSON.stringify({protocol_version:1,session_id:'session',...data})})};
}
const capabilities={terminology_normalizer:1,translation_engine:1,caption_overlay:1,persistent_captions:1,caption_latency:1,operator_console:1,captions_clear:1};
module.exports=(async()=>{
  const r=await rig();
  assert.equal(r.get('session-state').textContent,'IDLE');assert.equal(r.get('stop').disabled,true);
  assert.match(r.get('translator').textContent,/not verified/);
  assert.match(r.get('overlay-diagnostics').textContent,/latest —/);
  await r.get('start').onclick();await r.get('start').onclick();assert.equal(r.sockets.length,1);
  assert.equal(r.get('session-state').textContent,'STARTING');
  assert.deepEqual(Array.from(r.sockets[0].protocols),['operator.v1','private-control']);
  await r.send({type:'config',capabilities,translation_status:{state:'ready',provider:'deepl'}});
  assert.equal(r.get('session-state').textContent,'LIVE');assert.equal(r.get('stop').disabled,false);
  Object.assign(r.status,{state:'live',session_id:'session',owns_session:true,can_start:false,overlay_connections:2});
  await r.context.OperatorUI.refresh();assert.equal(r.get('clear').disabled,false);
  r.get('english').textContent='English history.';r.get('normalized').textContent='Historia normalizada.';r.get('confirmed').textContent='ASR history.';
  await r.get('clear').onclick();
  assert.equal(r.get('english').textContent,'English history.');assert.equal(r.get('normalized').textContent,'Historia normalizada.');
  assert.equal(r.get('confirmed').textContent,'ASR history.');assert.equal(r.get('session-state').textContent,'LIVE');
  const control=r.requests.find(request=>request.url.includes('/clear'));
  assert.equal(control.options.headers['X-Operator-Token'],'private-control');
  assert.equal(JSON.parse(control.options.body).session_id,'session');
  await r.send({type:'translation',translation:{sequence:1,segment_id:'session:1',provider:'deepl',success:false,
    error:'HTTP Error 403: PRIVATE_KEY',latency_ms:10,queue_delay_ms:0,attempt_count:1}});
  assert.match(r.get('error').textContent,/autenticación/);assert.doesNotMatch(r.get('english-segments').textContent,/PRIVATE_KEY/);
  assert.equal(r.get('session-state').textContent,'LIVE');
  await r.send({type:'translation',translation:{sequence:2,segment_id:'session:2',provider:'deepl',success:true,
    translated_text:'Recovered translation.',latency_ms:10,queue_delay_ms:0,attempt_count:1}});
  assert.equal(r.get('error').textContent,'');assert.equal(r.get('english').textContent,'Recovered translation.');
  r.status.latency_diagnostics.translation_queue_depth=3;
  await r.context.OperatorUI.refresh();assert.equal(r.get('latency-alert').textContent,'');
  r.advance(6000);await r.context.OperatorUI.refresh();assert.match(r.get('latency-alert').textContent,/acumulada/);
  await r.get('stop').onclick();assert.equal(r.get('session-state').textContent,'STOPPING');
  assert.equal(r.sent.length,1);assert.equal(r.sent[0].byteLength,0); // Existing FIFO flush reaches binary EOF.
  assert.equal(r.get('start').disabled,true);assert.equal(r.get('clear').disabled,true);
  await r.send({type:'status',state:'stopped'});await r.sockets[0].onclose();
  Object.assign(r.status,{state:'stopped',can_start:true});await r.context.OperatorUI.refresh();
  assert.equal(r.get('session-state').textContent,'STOPPED');assert.equal(r.get('start').disabled,false);
  await r.get('start').onclick();assert.equal(r.get('english').textContent,'');
  const old=await rig({old:true});await old.get('start').onclick();
  assert.equal(old.sockets.length,0);assert.equal(old.get('start').disabled,true);assert.match(old.get('error').textContent,/incompatibles/);
  const denied=await rig({microphoneError:{name:'NotAllowedError'}});await denied.get('start').onclick();
  assert.match(denied.get('error').textContent,/denegado/);assert.equal(denied.get('start').disabled,false);
  const incompatible=await rig();await incompatible.get('start').onclick();
  await incompatible.send({protocol_version:0,type:'config'});assert.match(incompatible.get('error').textContent,/incompatibles/);
  const b=await rig({bidirectional:true});
  assert.equal(b.get('direction').value,'en-es');assert.equal(b.get('direction').disabled,false);
  assert.equal(b.get('translation-label').textContent,'ESPAÑOL');
  await b.get('start').onclick();assert.match(b.sockets[0].url,/direction=en-es$/);
  assert.equal(b.get('direction').disabled,true);
  b.get('direction').value='es-en';b.get('direction').onchange();assert.equal(b.get('direction').value,'en-es');
  await b.send({type:'config',capabilities:{...capabilities,session_direction:1},direction:{id:'en-es'},translation_status:{state:'ready',provider:'test'}});
  Object.assign(b.status,{state:'live',can_start:false,can_change_direction:false,session_open:true,direction:{id:'en-es'},session_id:'session'});
  await b.context.OperatorUI.refresh();assert.equal(b.get('direction').disabled,true);
  await b.get('stop').onclick();assert.equal(b.get('direction').disabled,true);
  await b.send({type:'status',state:'stopped'});await b.sockets[0].onclose();
  Object.assign(b.status,{state:'stopped',session_open:false,can_start:false,can_change_direction:false,requires_stop_acknowledgement:true});
  await b.context.OperatorUI.refresh();assert.equal(b.get('direction').disabled,true);
  Object.assign(b.status,{can_start:true,can_change_direction:true,requires_stop_acknowledgement:false});
  await b.context.OperatorUI.refresh();
  b.get('direction').value='es-en';b.get('direction').onchange();
  assert.equal(b.get('translation-label').textContent,'ENGLISH');assert.equal(b.get('normalized-label').textContent,'NORMALIZED ES');
  await b.get('start').onclick();assert.match(b.sockets[1].url,/direction=es-en$/);
  assert.equal(b.get('english').textContent,'');
  const mismatch=await rig({bidirectional:true});await mismatch.get('start').onclick();
  await mismatch.send({type:'config',capabilities:{...capabilities,session_direction:1},direction:{id:'es-en'}});
  assert.match(mismatch.get('error').textContent,/incompatibles/);
  console.log('PASS: operator state machine, auth, CLEAR/history, EOF, metrics, sustained alerts, old backend and microphone errors');
})();
