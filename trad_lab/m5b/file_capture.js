"use strict";
function pcmFromFile(bytes,name){
  if(name.endsWith('.s16le')){if(bytes.byteLength%2)throw Error('PCM impar');return bytes;}
  const v=new DataView(bytes),ascii=(at,n)=>String.fromCharCode(...new Uint8Array(bytes,at,n));
  if(bytes.byteLength<12 || ascii(0,4)!=='RIFF' || ascii(8,4)!=='WAVE')throw Error('WAV RIFF requerido');
  let valid=false,pcm=null;
  for(let at=12;at+8<=bytes.byteLength;){
    const kind=ascii(at,4),size=v.getUint32(at+4,true),start=at+8;
    if(start+size>bytes.byteLength)throw Error('WAV truncado');
    if(kind==='fmt '){if(size<16 || v.getUint16(start,true)!==1 || v.getUint16(start+2,true)!==1 || v.getUint32(start+4,true)!==16000 || v.getUint16(start+14,true)!==16)throw Error('Solo PCM mono 16 kHz s16');valid=true;}
    if(kind==='data'){if(pcm)throw Error('WAV data duplicado');pcm=bytes.slice(start,start+size);}
    at=start+size+(size%2);
  }
  if(!valid || !pcm || pcm.byteLength%2)throw Error('WAV PCM incompleto');return pcm;
}
function availabilityDelay(mode,endBytes,origin,now){
  if(!['realtime','accelerated'].includes(mode))throw Error('Velocidad experimental inválida');
  return mode==='realtime'?Math.max(0,origin+endBytes/32-now):0;
}
class FrameCredit{
  constructor(seconds){this.seconds=seconds;this.pending=null;this.sent=0;this.frames=0;this.acked=0;}
  submit(bytes,sha256){
    if(this.pending)throw Error('Bloque anterior sin crédito');
    let resolve,reject;
    const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});
    // Attach a handler immediately; wait() still observes the same rejection.
    promise.catch(()=>{});
    this.pending={expected:{frame_sequence:this.frames,bytes,received_bytes:this.sent+bytes,sha256},promise,resolve,reject};
    this.frames++;this.sent+=bytes;
  }
  accept(message){
    if(!this.pending || Object.entries(this.pending.expected).some(([k,v])=>message[k]!==v))throw Error('Crédito PCM fuera de secuencia o SHA');
    this.acked+=this.pending.expected.bytes;
    this.pending.resolve();this.pending=null;
  }
  async wait(){
    if(!this.pending)return;
    let timer;
    try{await Promise.race([this.pending.promise,new Promise((_,no)=>{timer=setTimeout(()=>no(Error('Sin crédito PCM; sesión incompleta')),this.seconds*1000);})]);}
    finally{clearTimeout(timer);}
  }
  fail(error){if(this.pending)this.pending.reject(error);}
}
if(typeof module!=='undefined')module.exports={pcmFromFile,availabilityDelay,FrameCredit};
if(typeof document!=='undefined'){
  const status=document.getElementById('status'),button=document.getElementById('replay'),file=document.getElementById('pcm');
  let owner=null,pcm=null,socket=null,stopping=false,eof=false,started=false,failed=false,sent=0,terminal=false,gate=null;
  const pacing=document.getElementById('pacing');
  const hex=b=>Array.from(new Uint8Array(b),x=>x.toString(16).padStart(2,'0')).join('');
  const tell=type=>window.opener?.postMessage({type},location.origin);
  const error=e=>{failed=true;gate?.fail(e);status.textContent=String(e.message || e);button.disabled=true;if(socket)socket.close();tell('capture_failed');};
  function finish(){if(eof || socket?.readyState!==WebSocket.OPEN)return;eof=true;socket.send(new ArrayBuffer(0));status.textContent=`Drenando; ${sent} bytes enviados. No cerrar.`;}
  addEventListener('message',e=>{
    if(e.origin!==location.origin || e.source!==window.opener || e.data?.type!=='capture_start' || owner || started)return;
    if(e.data.direction!=='en-es' || typeof e.data.token!=='string')return;
    owner=e.data.token;button.disabled=!pcm;status.textContent='Propietario recibido; selecciona el PCM verificado y pulsa REPLAY.';
  });
  file.onchange=async()=>{
    try{
      if(started)throw Error('Una reproducción por ventana');
      const selected=file.files[0];if(!selected || selected.size>64000000)throw Error('Archivo ausente o demasiado grande');
      const bytes=await selected.arrayBuffer(),sha=hex(await crypto.subtle.digest('SHA-256',bytes));
      const allowed=await (await fetch('/static/m5b_inputs.json',{cache:'no-store'})).json();
      const entry=allowed.find(s=>s.sha256===sha);if(!entry)throw Error('Archivo fuera del manifiesto M5-A');
      pcm=pcmFromFile(bytes,selected.name);
      if(hex(await crypto.subtle.digest('SHA-256',pcm))!==entry.pcm_sha256)throw Error('PCM no coincide');
      status.textContent=`PCM verificado ${entry.id}, ${pcm.byteLength} bytes. Sin micrófono.`;button.disabled=!owner;
    }catch(e){error(e);}
  };
  button.onclick=()=>{
    if(started || !owner || !pcm)return;started=true;button.disabled=true;file.disabled=true;pacing.disabled=true;
    socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/session?direction=en-es`,['operator.v1',owner]);
    socket.onmessage=async e=>{
      try{
        const m=JSON.parse(e.data);if(m.protocol_version!==1)throw Error('Protocolo incompatible');
        if(m.type==='error')throw Error(m.message || 'Error de integración');
        if(m.type==='pcm_ack'){if(!gate)throw Error('Crédito sin configuración');gate.accept(m);}
        if(m.type==='operator_command' && m.command==='stop'){stopping=true;finish();}
        if(m.type==='asr' && m.payload?.type==='ready_to_stop')terminal=true;
        if(m.type==='status' && m.state==='stopped')status.textContent=JSON.stringify({transport:m.completion,asr:m.experimental_asr,sent_bytes:sent,acked_bytes:gate?.acked,whole_file:sent===pcm.byteLength,terminal,pacing:pacing.value},null,2);
        if(m.type==='config'){
          if(m.wlk?.session_language!=='en' || m.wlk?.session_language_isolation!==1)throw Error('Inglés no atestiguado');
          if(gate || m.experimental_transport?.pcm_credit!==1 || m.experimental_transport?.frame_bytes!==64000)throw Error('Control de flujo no atestiguado');
          const seconds=m.experimental_transport.credit_seconds;
          if(!Number.isFinite(seconds) || seconds<=0 || seconds>39)throw Error('Plazo de crédito inválido');
          gate=new FrameCredit(seconds);const origin=performance.now();
          for(let at=0;at<pcm.byteLength && !stopping;at+=64000){
            await gate.wait();
            const end=Math.min(at+64000,pcm.byteLength);
            const delay=availabilityDelay(pacing.value,end,origin,performance.now());
            if(delay)await new Promise(r=>setTimeout(r,delay));
            if(stopping)break;
            if(socket.readyState!==WebSocket.OPEN)throw Error('Transporte cerrado');
            const block=pcm.slice(at,end),sha=hex(await crypto.subtle.digest('SHA-256',block));
            if(stopping)break;
            gate.submit(block.byteLength,sha);socket.send(block);sent+=block.byteLength;
          }
          await gate.wait();
          finish();
        }
      }catch(e){error(e);}
    };
    socket.onerror=()=>error(Error('Fallo WebSocket experimental'));
    socket.onclose=()=>{if(!terminal && !failed)error(Error('Cierre sin terminal'));tell(failed?'capture_failed':'capture_closed');};
  };
  document.getElementById('stop').onclick=()=>{stopping=true;finish();};
  fetch('/api/operator/bootstrap',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Autorización local rechazada');tell('capture_ready');}).catch(error);
}
