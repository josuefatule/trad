/* Lab-only fail-closed START barrier. Installed before browser.js/app scripts. */
(() => {
  if(location.port!=='18010' || !['127.0.0.1','localhost'].includes(location.hostname))return;
  if(globalThis.__m4bGate)return;
  let pendingReady=null,replaying=false,released=false,readyTimer=null;
  let approved=false,broken=false,reason='Instrumentación M4-B pendiente',resolveReady,rejectReady;
  const waiting=new Promise((resolve,reject)=>{resolveReady=resolve;rejectReady=reject;});
  // The rejection is also observable by a waiting capture; prevent an unhandled
  // rejection if no capture was requested (the normal no-audio preparation).
  waiting.catch(()=>{});
  const block=()=>{
    const start=document.getElementById('start');
    if((!approved || globalThis.__m4bNoAudio===true) && start && !start.disabled)start.disabled=true;
  };
  globalThis.__m4bGate={
    state:()=>({approved,failed:broken,reason,no_audio:globalThis.__m4bNoAudio===true,
      owner_barrier:true,capture_pending:!!pendingReady,capture_released:released}),
    approve:page=>{
      const s=globalThis.__m4bState?.();
      if(broken || !s || s.page!==page || !s.dom_ready || !s.ready_acknowledged || s.failed ||
          !Object.values(s.observers).every(Boolean))throw Error('M4B_NOT_PREPARED');
      approved=true;reason=null;resolveReady();globalThis.OperatorUI?.render();return true;
    },
    fail:code=>{approved=false;broken=true;reason=code;pendingReady=null;clearTimeout(readyTimer);block();rejectReady(Error(code));},
    releaseCapture:page=>{
      if(broken || !approved || globalThis.__m4bNoAudio===true || !pendingReady || released)throw Error('M4B_OWNER_NOT_PREPARED');
      const child=pendingReady.source;
      const state=child.__m4bState?.(),gate=child.__m4bGate?.state();
      if(child.closed || child.opener!==window || child.location.pathname!=='/capture' || !state || state.page!==page ||
          state.failed || !state.dom_ready || !state.ready_acknowledged || !Object.values(state.observers).every(Boolean) ||
          !gate?.approved || gate.failed || gate.no_audio)throw Error('M4B_CHILD_NOT_PREPARED');
      // A stopped native MessageEvent must not carry its dispatch flags into
      // release. Preserve its source/origin/data/ports in a fresh event; the
      // operational listener still creates capture_start itself, unchanged.
      const held=pendingReady;pendingReady=null;released=true;clearTimeout(readyTimer);replaying=true;
      const ready=new MessageEvent('message',{source:held.source,origin:held.origin,data:held.data,
        ports:held.ports || [],lastEventId:held.lastEventId || ''});
      try{window.dispatchEvent(ready);}finally{replaying=false;}
      return true;
    },
    wait:async()=>{
      if(globalThis.__m4bNoAudio===true)throw Error('M4B_NO_AUDIO_VALIDATION');
      if(approved)return;
      let timer;
      try{await Promise.race([waiting,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('M4B_PREPARATION_TIMEOUT')),5000);})]);}
      finally{clearTimeout(timer);}
      if(!approved)throw Error('M4B_NOT_PREPARED');
    }
  };
  window.addEventListener('message',event=>{
    if(event.origin!==location.origin)return;
    if(location.pathname==='/operator' && event.data?.type==='capture_ready' && !replaying){
      event.stopImmediatePropagation();
      if(broken || !approved || released)return;
      try{if(!event.source || event.source.opener!==window || event.source.location.pathname!=='/capture')return;}
      catch{return;}
      if(pendingReady && pendingReady.source!==event.source){globalThis.__m4bGate.fail('M4B_MULTIPLE_CAPTURE_WINDOWS');return;}
      pendingReady=event;
      clearTimeout(readyTimer);
      readyTimer=setTimeout(()=>globalThis.__m4bGate.fail('M4B_POPUP_PREPARATION_TIMEOUT'),10000);
    }
    if(location.pathname==='/capture' && event.source===window.opener && event.data?.type==='capture_start' &&
        (!approved || broken || globalThis.__m4bNoAudio===true)){
      event.stopImmediatePropagation();globalThis.__m4bGate.fail('M4B_CAPTURE_START_BEFORE_PREPARATION');
    }
  },true);
  window.addEventListener('click',e=>{
    if((!approved || globalThis.__m4bNoAudio===true) && e.target.closest?.('#start')){
      e.preventDefault();e.stopImmediatePropagation();block();
      const notice=document.getElementById('control-notice');if(notice)notice.textContent=reason;
    }
  },true);
  const initializeDOM=()=>{
    block();const start=document.getElementById('start');
    if(start)new MutationObserver(block).observe(start,{attributes:true,attributeFilter:['disabled']});
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initializeDOM,{once:true});
  else initializeDOM();
})();
