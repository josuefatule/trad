// Regression for the parent releasing capture_start before child observers.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const guard=fs.readFileSync('trad_lab/m4b/guard.js','utf8');
function surface(path,noAudio=false){
  const listeners={},start={disabled:false},timers=new Map();let serial=0;
  const c={location:{port:'18010',hostname:'127.0.0.1',origin:'http://127.0.0.1:18010',pathname:path},
    __m4bNoAudio:noAudio,document:{readyState:'complete',getElementById:id=>id==='start'?start:null},
    MessageEvent:class{constructor(type,init){this.type=type;Object.assign(this,init);}},
    MutationObserver:class{observe(){}},setTimeout:f=>{timers.set(++serial,f);return serial;},clearTimeout:id=>timers.delete(id),
    addEventListener:(name,f)=>{(listeners[name]??=[]).push(f);},OperatorUI:{render(){start.disabled=false;}}};
  c.window=c;c.dispatchEvent=event=>{
    // Preserve the stopped native event's flag across a delayed redispatch.
    // Reusing it used to pass this double but failed in real Chrome.
    if(event.stopped)return true;
    event.stopped=false;event.stopImmediatePropagation=()=>{event.stopped=true;};
    for(const f of listeners.message||[]){f(event);if(event.stopped)break;}return true;
  };
  c.state={page:path,dom_ready:true,ready_acknowledged:true,failed:false,
    observers:dictObservers()};c.__m4bState=()=>c.state;
  vm.createContext(c);vm.runInContext(guard,c);
  return {c,proxy:vm.runInContext('window',c),start,listeners,timers};
}
function dictObservers(){return Object.fromEntries(['media','worklet','worker','websocket','dom','controls'].map(k=>[k,true]));}
function ownerFixture(noAudio=false){
  const owner=surface('/operator',noAudio),child=surface('/capture');
  child.c.opener=owner.proxy;child.c.closed=false;
  let delivered=0,lastEvent=null,lastPayload=null;
  const ready={type:'message',origin:owner.c.location.origin,source:child.proxy,data:{type:'capture_ready'}};
  const payload={type:'capture_start',token:'private-test-only',deviceId:'exact-device',direction:'en-es'};
  owner.c.addEventListener('message',event=>{
    if(event.origin===owner.c.location.origin && event.source===child.proxy && event.data.type==='capture_ready'){
      delivered++;lastEvent=event;lastPayload=payload;
    }
  });
  owner.c.__m4bGate.approve('/operator');
  return {owner,child,ready,payload,delivered:()=>delivered,event:()=>lastEvent,payloadSeen:()=>lastPayload};
}
{
  const f=ownerFixture();f.owner.c.dispatchEvent(f.ready);
  assert.equal(f.delivered(),0);assert(f.owner.c.__m4bGate.state().capture_pending);
  assert.throws(()=>f.owner.c.__m4bGate.releaseCapture('/capture'));
  f.child.c.__m4bGate.approve('/capture');f.child.c.state.ready_acknowledged=false;
  assert.throws(()=>f.owner.c.__m4bGate.releaseCapture('/capture'));
  f.child.c.state.ready_acknowledged=true;
  assert.throws(()=>f.owner.c.__m4bGate.releaseCapture('stale'));
  assert.equal(f.owner.c.__m4bGate.releaseCapture('/capture'),true);
  assert.equal(f.delivered(),1);assert.notEqual(f.event(),f.ready);assert.equal(f.event().data,f.ready.data);
  assert.equal(f.event().source,f.child.proxy);assert.equal(f.payloadSeen(),f.payload);
  assert.equal(f.owner.timers.size,0);assert.throws(()=>f.owner.c.__m4bGate.releaseCapture('/capture'));
}
for(const fail of ['missing-child-guard','failed-owner','no-audio','timeout']){
  const f=ownerFixture(fail==='no-audio');f.owner.c.dispatchEvent(f.ready);f.child.c.__m4bGate.approve('/capture');
  if(fail==='missing-child-guard')vm.runInContext('globalThis.__m4bGate=undefined',f.child.c);
  if(fail==='failed-owner')f.owner.c.__m4bGate.fail('test-failure');
  if(fail==='timeout')for(const timer of f.owner.timers.values())timer();
  assert.throws(()=>f.owner.c.__m4bGate.releaseCapture('/capture'),fail);
  assert.equal(f.delivered(),0,fail);
}
{
  const {owner,child}=ownerFixture();let starts=0;
  child.c.addEventListener('message',()=>starts++);
  child.c.dispatchEvent({type:'message',origin:child.c.location.origin,source:owner.proxy,data:{type:'capture_start'}});
  assert.equal(starts,0);assert(child.c.__m4bGate.state().failed);
}
console.log('PASS: owner retains ready, rejects missing/failed/stale/timeout/no-audio child, releases exactly once in fresh event with identical source/data; child rejects early capture_start. No real audio.');
