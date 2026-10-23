/* Installed before application scripts by CDP, only on isolated origin 18010.
 * Observers never alter auth, websocket payloads or microphone constraints.
 * Audio disk writing happens in the Python collector's bounded writer thread. */
(() => {
  'use strict';
  if(location.port!=='18010' || !['127.0.0.1','localhost'].includes(location.hostname))return;
  if(globalThis.__m4bState)return;
  const page=crypto.randomUUID(), epoch=performance.timeOrigin;
  const queue=[];let bytes=0,inflight=null,packet=0,failed=false,contextSerial=0,session=null,domReady=false,readyAck=false;
  let readyAt=null,firstBlock=null,eofAt=null,meta=null,preSeq=0,sentSeq=0;
  const seenReady=new Set(), channel=new BroadcastChannel('m4b-diagnostic-only');
  const stamp=()=>performance.now();
  const warn=reason=>{failed=true;globalThis.__m4bGate?.fail(reason);const n=document.getElementById('m4b-state');if(n)n.textContent='EVIDENCIA INVÁLIDA: '+reason;};
  function emit(kind,fields={}) {
    if(failed)return;
    const row={kind,page,ms:stamp(),epoch_ms:epoch,session_id:session,...fields};
    const encoded=JSON.stringify(row);
    if(encoded.length>200000 || bytes+encoded.length>8*1024*1024){warn('buffer excedido; pulsa STOP');return;}
    queue.push(encoded);bytes+=encoded.length;
  }
  function b64(buffer) {
    const a=new Uint8Array(buffer);let s='';
    for(let i=0;i<a.length;i+=16384)s+=String.fromCharCode(...a.subarray(i,i+16384));
    return btoa(s);
  }
  globalThis.__m4bAck=id=>{if(inflight?.id===id){if(inflight.ready)readyAck=true;inflight=null;}};
  globalThis.__m4bState=()=>({page,failed,pending:queue.length,inflight:!!inflight,eof:eofAt!==null,session_id:session,
    dom_ready:domReady,ready_acknowledged:readyAck,observers:{
      media:navigator.mediaDevices.getUserMedia===installed.media,worklet:globalThis.AudioWorkletNode===installed.worklet,
      worker:globalThis.Worker===installed.worker,websocket:globalThis.WebSocket===installed.websocket,
      dom:domReady,controls:!!globalThis.__m4bGate}});
  setInterval(()=>{
    if(inflight && stamp()-inflight.at>5000){warn('sin ACK del escritor; pulsa STOP');return;}
    if(inflight || !queue.length || failed)return;
    const rows=[];let size=2;
    while(queue.length && size+queue[0].length+1<180000){const s=queue.shift();bytes-=s.length;size+=s.length+1;rows.push(s);}
    const id=++packet;inflight={id,at:stamp(),ready:rows.some(s=>JSON.parse(s).kind==='observers_ready')};
    globalThis.__m4bBinding(JSON.stringify({id,page,rows:JSON.parse('['+rows.join(',')+']')}));
  },50);
  setInterval(()=>{emit('clock',{date_ms:Date.now(),performance_ms:stamp()});},2000);
  if(typeof globalThis.fetch==='function') {
    const originalFetch=globalThis.fetch.bind(globalThis);
    globalThis.fetch=async(...args)=>{
      const response=await originalFetch(...args);
      const url=new URL(typeof args[0]==='string'?args[0]:args[0].url,location.href);
      if(url.origin===new URL(location.href).origin && /^\/api\/operator\/(clear|stop)$/.test(url.pathname)) {
        response.clone().json().then(m=>{
          emit('control_result',{control:url.pathname.endsWith('/clear')?'clear':'stop',http_status:response.status,
            applied:m.applied,session_id:m.session_id,visual_generation:m.visual_generation});
          if(url.pathname.endsWith('/clear') && m.applied===true){
            const overlay=document.getElementById('m4b-overlay');if(overlay)overlay.textContent='';
            emit('overlay_clear',{visual_generation:m.visual_generation});
          }
        }).catch(()=>{});
      }
      return response;
    };
  }

  // Record the effective browser/track settings; omit device/group identifiers.
  const gum=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia=async constraints=>{
    emit('media_requested');
    if(!globalThis.__m4bGate)throw Error('M4B_GUARD_MISSING');
    await globalThis.__m4bGate.wait();
    const stream=await gum(constraints);
    for(const track of stream.getAudioTracks()) {
      const s=track.getSettings();emit('track',{label:track.label,settings:Object.fromEntries([
        'sampleRate','channelCount','echoCancellation','noiseSuppression','autoGainControl','latency'
      ].filter(k=>k in s).map(k=>[k,s[k]]))});
    }
    return stream;
  };
  const OriginalNode=globalThis.AudioWorkletNode;
  globalThis.AudioWorkletNode=class extends OriginalNode {
    constructor(context,name,options) {
      super(context,name,options);
      const ctx=++contextSerial;
      emit('worklet_created',{context:ctx,sample_rate:context.sampleRate,state:context.state,configured_channels:options?.channelCount});
      this.port.addEventListener('message',e=>{
        if(e.data?.m4b) {
          meta=e.data;e.stopImmediatePropagation();return;
        }
        if(e.data instanceof Float32Array) {
          if(!meta){warn('falta metadata AudioWorklet');return;}
          const output=context.getOutputTimestamp?.();
          if(firstBlock===null){firstBlock=stamp();emit('first_audio_block');channel.postMessage({kind:'first_block',at:epoch+firstBlock});}
          emit('pre',{seq:preSeq++,samples:e.data.length,sample_rate:meta.rate,channels:meta.channels,
            frame:meta.frame,context:ctx,context_s:context.currentTime,output_timestamp:output,
            b64:b64(e.data.buffer)});
          meta=null;
        } else if(e.data?.flushed)emit('worklet_flushed');
      });
      this.port.start();
    }
  };
  const OriginalWorker=globalThis.Worker;
  globalThis.Worker=class extends OriginalWorker {
    constructor(url,options){
      super(url,options);
      if(!String(url).includes('recorder_worker.js'))return;
      const post=this.postMessage.bind(this);
      this.postMessage=(m,...args)=>{if(m.command==='init')emit('worker_init',{config:m.config});if(m.command==='flush')emit('worker_flush_requested');return post(m,...args);};
      this.addEventListener('message',e=>{if(e.data.flushed)emit('worker_flushed');});
    }
  };
  const allowed=['type','state','session_id','protocol_version','direction','capabilities','wlk','payload','transcript','segmentation','normalization','outcome','completion','translation_metrics','translation_status','reliability'];
  const scrub=x=>Array.isArray(x)?x.map(scrub):x&&typeof x==='object'?Object.fromEntries(Object.entries(x).filter(([k])=>!/token|secret|nonce|authorization|cookie|api_key|auth_key/i.test(k)).map(([k,v])=>[k,scrub(v)])):x;
  function segments(message) {
    for(const seg of message.segmentation?.ready_segments || []) {
      const id=message.session_id+':'+seg.id;
      if(seenReady.has(id))continue;seenReady.add(id);
      emit('ready',{segment:seg});channel.postMessage({kind:'ready',session_id:message.session_id,segment:seg});
    }
  }
  const OriginalSocket=globalThis.WebSocket;
  globalThis.WebSocket=class extends OriginalSocket {
    constructor(url,protocols) {
      super(url,protocols);
      if(new URL(url,location.href).pathname!=='/ws/session')return;
      emit('capture_socket_created');
      this.addEventListener('open',()=>emit('socket_open'));
      this.addEventListener('close',e=>emit('socket_closed',{code:e.code,clean:e.wasClean}));
      this.addEventListener('message',e=>{
        if(typeof e.data!=='string')return;
        let m;try{m=JSON.parse(e.data);}catch{return;}
        if(m.session_id)session=m.session_id;
        emit('browser_frame',{message:scrub(Object.fromEntries(allowed.filter(k=>k in m).map(k=>[k,m[k]])))});
        segments(m);
        if(m.type==='config') {
          if(m.direction?.source_language!=='en' || m.wlk?.session_language!=='en' || m.wlk?.session_language_isolation!==1)warn('handshake inglés no verificado');
          emit('handshake',{pcm:m.wlk?.useAudioWorklet,language:m.wlk?.session_language});
        }
        if(m.type==='status' && m.state==='stopped')channel.postMessage({kind:'stopped',session_id:session,outcome:m.completion || m.outcome || m.reliability?.outcome});
      });
      const send=this.send.bind(this);
      this.send=data=>{
        const result=send(data);
        if(data instanceof ArrayBuffer) {
          emit('sent',{seq:sentSeq++,samples:data.byteLength/2,b64:b64(data),buffered_amount:this.bufferedAmount});
          if(data.byteLength===0){eofAt=stamp();emit('binary_eof');channel.postMessage({kind:'eof',session_id:session});}
        }
        return result;
      };
    }
  };

  const installed={media:navigator.mediaDevices.getUserMedia,worklet:globalThis.AudioWorkletNode,worker:globalThis.Worker,websocket:globalThis.WebSocket};
  const initializeDOM=()=>{
    if(domReady)return;
    emit('document_ready',{surface:location.pathname});
    for(const id of ['partial','confirmed','pending','ready','normalized','english']) {
      const node=document.getElementById(id);if(!node)continue;
      new MutationObserver(()=>{
        emit('dom',{element:id,text:node.textContent.slice(-60000)});
        requestAnimationFrame(()=>emit('paint_opportunity',{element:id,visibility:document.visibilityState}));
      }).observe(node,{subtree:true,childList:true,characterData:true});
    }
    for(const id of ['start','stop','clear'])document.getElementById(id)?.addEventListener('click',()=>emit('control_click',{control:id}),true);
    domReady=true;emit('observers_ready',{surface:location.pathname});
    if(location.pathname!=='/operator')return;
    const panel=document.createElement('section');panel.style.cssText='background:#152333;color:white;padding:16px;position:relative;z-index:10';
    panel.innerHTML='<strong>M4-B / SOLO DIAGNÓSTICO INGLÉS / DeepL OFF</strong><p id="m4b-state">Selecciona Blue Yeti, START y espera CAPTURE.</p><p>MP3 cardio_01: <input id="m4b-file" type="file" accept="audio/mpeg"></p><audio id="m4b-audio" controls></audio><button id="m4b-play" disabled>Reproducir 0–100 s tras preroll</button><p>Tras terminar, espera 5 s y pulsa STOP normal. CLEAR puede probarse durante el postroll.</p><div id="m4b-overlay" aria-label="Overlay experimental ASR inglés"></div>';
    document.body.prepend(panel);
    const player=document.getElementById('m4b-audio'),button=document.getElementById('m4b-play'),state=document.getElementById('m4b-state'),overlay=document.getElementById('m4b-overlay');
    let refURL=null,referenceValid=false,playing=false;
    document.getElementById('m4b-file').onchange=async e=>{
      const f=e.target.files[0];if(!f)return;
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await f.arrayBuffer()))).map(n=>n.toString(16).padStart(2,'0')).join('');
      referenceValid=hash==='59d1ec58514134f7bf326d824e33f61eb868713b71cad147395563104119a25d';
      emit('reference_file',{sha256:hash,bytes:f.size,valid:referenceValid});
      if(refURL)URL.revokeObjectURL(refURL);refURL=URL.createObjectURL(f);player.src=refURL;
      if(!referenceValid)state.textContent='MP3 distinto: no iniciar reproducción.';
    };
    // Hide native controls: the guarded button is the only playback action.
    player.controls=false;
    button.onclick=async()=>{
      if(failed || !referenceValid || !readyAt || performance.timeOrigin+stamp()-readyAt<5000)return;
      player.currentTime=0;emit('reference_play_requested',{start_s:0,duration_s:100});
      try{await player.play();}catch{warn('reproducción bloqueada');}
    };
    player.addEventListener('playing',()=>{playing=true;emit('reference_playing',{media_s:player.currentTime,ready_epoch_ms:readyAt,
      caution:'Browser playing event; speaker/acoustic onset requires waveform alignment'});});
    player.addEventListener('pause',()=>{if(playing){playing=false;emit('reference_paused',{media_s:player.currentTime});}});
    // A separate diagnostic overlay, never an OBS/Spanish translation claim.
    channel.onmessage=e=>{
      const m=e.data;
      if(m.kind==='first_block'){readyAt=m.at;state.textContent='PCM fluye. Espera 5 s; luego reproduce el MP3 validado.';emit('capture_flow_observed',{capture_epoch_ms:m.at});}
      if(m.kind==='ready'){
        session=m.session_id;overlay.textContent=m.segment.text;
        emit('overlay_dom',{segment_id:m.segment.id,text:m.segment.text});
        requestAnimationFrame(()=>emit('overlay_paint_opportunity',{segment_id:m.segment.id,visibility:document.visibilityState}));
      }
      if(m.kind==='eof')emit('capture_eof_observed');
      if(m.kind==='stopped'){emit('terminal_observed',{outcome:m.outcome});state.textContent='STOP observado. Espera a que el colector termine.';button.disabled=true;}
    };
    setInterval(()=>{
      button.disabled=failed || !referenceValid || readyAt===null || performance.timeOrigin+stamp()-readyAt<5000 || playing;
      if(playing && player.currentTime>=100){player.pause();emit('reference_end',{media_s:player.currentTime});state.textContent='Referencia finalizada: espera 5 s y pulsa STOP.';}
    },25);
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initializeDOM,{once:true});
  else initializeDOM();
})();
