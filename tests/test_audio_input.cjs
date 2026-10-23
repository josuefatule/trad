const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../app/static');
const usb={kind:'audioinput',deviceId:'usb-interface-exact-id',label:'Microphone (USB AUDIO DEVICE)'};
const builtin={kind:'audioinput',deviceId:'builtin-id',label:'Microphone Array'};
async function rig({capture=false,saved=new Map(),delayed=false}={}){
  const nodes=new Map(),events=new Map(),mediaEvents=new Map(),requests=[],sockets=[];
  let devices=[builtin,usb],enumerations=0,resolveDevices;
  const pending=new Promise(resolve=>resolveDevices=resolve);
  const get=id=>{
    if(!nodes.has(id)){
      let value='',options=[];
      nodes.set(id,{textContent:'',dataset:{},disabled:false,
        get value(){return value;},set value(next){value=id==='microphone'&&!options.some(o=>o.value===next)?'':next;},
        get selectedOptions(){return options.filter(o=>o.value===value);},
        replaceChildren(...next){options=next;value=next[0]?.value||'';}});
    }
    return nodes.get(id);
  };
  const opener={postMessage(){}};
  const win={opener,addEventListener:(type,fn)=>events.set(type,fn)};
  const track={label:usb.label,stop(){}};
  const context=vm.createContext({window:win,document:{getElementById:get,body:{classList:{add(){}}}},
    location:{protocol:'http:',host:'localhost:8010',origin:'http://localhost:8010',pathname:capture?'/capture':'/operator',search:''},
    URLSearchParams,Option:class{constructor(label,value){this.textContent=label;this.value=value;}},setTimeout(){},clearTimeout(){},
    localStorage:{getItem:key=>saved.get(key)||null,setItem:(key,value)=>saved.set(key,value),removeItem:key=>saved.delete(key)},
    sessionStorage:{getItem(){return null;},setItem(){}},
    navigator:{mediaDevices:{addEventListener:(type,fn)=>mediaEvents.set(type,fn),
      enumerateDevices:async()=>{enumerations++;return delayed?pending:devices;},
      getUserMedia:async constraints=>{requests.push(constraints);const id=constraints.audio?.deviceId?.exact;
        if(id&&!devices.some(d=>d.deviceId===id))throw {name:'OverconstrainedError'};
        return {getAudioTracks:()=>[track],getTracks:()=>[track]};}}},
    AudioContext:class{constructor(){this.state='running';}async resume(){}async close(){}},
    WebSocket:class{constructor(url){sockets.push(url);}close(){}},
    fetch:async url=>({ok:true,json:async()=>url.includes('bootstrap')?{protocol_version:1,capabilities:{operator_console:1,captions_clear:1,session_direction:1},control_token:'test',diagnostics_config:{}}:
      {protocol_version:1,state:'waiting',session_open:false,can_start:true,can_change_direction:true,caption_config:{},translator:{},latency_diagnostics:{},overlay_connections:0}})
  });
  for(const file of ['operator_console.js','operator.js']){
    vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context);
    if(file==='operator_console.js')context.OperatorConsole=win.OperatorConsole;
  }
  await context.OperatorUI.ready;
  if(!delayed)await context.microphones();
  return {get,context,requests,sockets,saved,opener,events,mediaEvents,
    setDevices:next=>devices=next,resolveDevices:()=>resolveDevices(devices),count:()=>enumerations};
}
(async()=>{
  const parent=await rig();
  parent.get('microphone').value=usb.deviceId;parent.get('microphone').onchange();
  assert.equal(JSON.parse(parent.saved.get('trad-audio-input-v1')).deviceId,usb.deviceId);
  assert.equal(parent.get('selected-microphone').textContent,usb.label);
  assert.equal(parent.requests.length,0);
  parent.setDevices([builtin]);await parent.context.microphones();
  assert.equal(parent.get('microphone').value,usb.deviceId);
  assert.match(parent.get('selected-microphone').textContent,/no disponible/);
  await parent.get('start').onclick();
  assert.equal(parent.requests[0].audio.deviceId.exact,usb.deviceId);
  assert.equal(parent.sockets.length,0); // Unplugging USB cannot silently open the builtin microphone.
  const restored=await rig({saved:parent.saved});
  assert.equal(restored.get('microphone').value,usb.deviceId);
  restored.get('microphone').value='';restored.get('microphone').onchange();await restored.context.microphones();
  assert.equal(restored.get('microphone').value,'');assert.equal(restored.saved.size,0);
  const count=restored.count();restored.context.OperatorUI.localActive=true;
  restored.mediaEvents.get('devicechange')();assert.equal(restored.count(),count);
  const popup=await rig({capture:true,delayed:true});
  assert.equal(popup.get('microphone').value,'');
  await popup.events.get('message')({origin:'http://localhost:8010',source:popup.opener,
    data:{type:'capture_start',token:'test',deviceId:usb.deviceId,direction:'en-es'}});
  assert.equal(popup.get('microphone').value,''); // Browser rejects values absent from the unpopulated select.
  assert.equal(popup.requests[0].audio.deviceId.exact,usb.deviceId);
  assert.equal(popup.sockets.length,1);
  popup.resolveDevices();
  console.log('PASS: USB exacto en CAPTURE con lista pendiente, preferencia persistente y sin fallback al desconectar.');
})().catch(error=>{console.error(error);process.exitCode=1;});
