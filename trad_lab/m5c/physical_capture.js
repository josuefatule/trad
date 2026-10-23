'use strict';
(async()=>{
  const status=document.getElementById('status'),start=document.getElementById('start'),stop=document.getElementById('stop');
  const caps=await (await fetch('/m5c/capabilities')).json();
  let owner=null,device=null,started=false,failed=false,stopping=false,terminal=false,stream,context,source,node,worker,socket,session,timer,pumping=false,dspMetadata=null;
  const q=new M5CPhysical.PCMQueue();
  const tell=type=>opener?.postMessage({type},location.origin);
  function release(){stream?.getTracks().forEach(t=>t.stop());source?.disconnect();node?.disconnect();worker?.terminate();context?.close();}
  function error(e){if(failed)return;failed=true;clearTimeout(timer);status.textContent='INCOMPLETE: '+e.message;start.disabled=true;stop.disabled=true;release();socket?.close();tell('capture_failed');}
  async function pump(){
    if(pumping||failed)return;pumping=true;
    try{
      const buffer=q.take();
      if(buffer){
        const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer)),x=>x.toString(16).padStart(2,'0')).join('');
        if(failed)return;q.hash(hash);
        if(socket.readyState!==WebSocket.OPEN||socket.bufferedAmount>64000)throw Error('Socket backlog exceeded');
        socket.send(buffer);timer=setTimeout(()=>error(Error('PCM credit timeout')),39000);
      }else if(q.finish()){socket.send(new ArrayBuffer(0));status.textContent='Drenando EOF; no cerrar';release();}
    }catch(e){error(e);}finally{pumping=false;}
  }
  function finish(){
    if(stopping||failed)return;stopping=true;stop.disabled=true;
    if(node)node.port.postMessage({command:'flush'});
    else if(session){q.flush();pump();}
  }
  addEventListener('message',e=>{
    if(e.origin!==location.origin||e.source!==opener||e.data?.type!=='capture_start'||owner||started)return;
    if(e.data.direction!=='en-es'||!e.data.deviceId){error(Error('Explicit EN→ES device required'));return;}
    owner=e.data.token;device=e.data.deviceId;
    status.textContent=caps.physical_enabled?'Propietario recibido. Verificar Yeti antes de voz.':'Propietario recibido. M5-C1 BLOQUEADO: requiere autorización M5-C2.';
    start.disabled=!caps.physical_enabled;
  });
  start.onclick=async()=>{
    if(started||!caps.physical_enabled||!owner||!device)return;started=true;start.disabled=true;
    try{
      // No native mic access until explicit future capability, owner and user click.
      stream=await navigator.mediaDevices.getUserMedia({audio:{deviceId:{exact:device},channelCount:1}});
      const track=stream.getAudioTracks()[0];
      if(!/yeti/i.test(track.label)||track.getSettings().deviceId!==device)throw Error('Effective Blue Yeti mismatch');
      context=new AudioContext();if(![16000,44100,48000].includes(context.sampleRate))throw Error('Unsupported context sample rate');
      socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/session?direction=en-es`,['operator.v1',owner]);
      socket.onmessage=async e=>{
        try{
          const m=JSON.parse(e.data);if(m.protocol_version!==1)throw Error('Protocol mismatch');
          if(m.type==='error')throw Error(m.message||'Session error');
          if(m.type==='config'){
            if(session||m.wlk?.session_language!=='en'||m.wlk?.session_language_isolation!==1||m.experimental_transport?.pcm_credit!==1||m.experimental_transport?.frame_bytes!==64000||m.experimental_transport?.credit_seconds!==39)throw Error('Credit/English handshake mismatch');
            session=m.session_id;
            if(stopping){q.flush();pump();return;}
            try{await context.audioWorklet.addModule('/static/m5c_worklet.js');}catch(e){if(stopping)return;throw e;}
            if(stopping)return;
            worker=new Worker('/static/m5c_worker.js');worker.postMessage({command:'init',sample_rate:context.sampleRate});
            node=new AudioWorkletNode(context,'m5c-forwarder',{numberOfInputs:1,numberOfOutputs:0,channelCount:1,channelCountMode:'explicit'});
            worker.onmessage=e=>{
              try{
                const m=e.data;if(m.error)throw Error(m.error);q.append(m.buffer);
                if(m.ack!==undefined)node.port.postMessage({command:'ack',sequence:m.ack});
                if(m.flushed){dspMetadata=m.metadata;if(dspMetadata.output_samples*2!==q.accepted)throw Error('DSP byte count mismatch');q.flush();}pump();
              }catch(e){error(e);}
            };
            worker.onerror=()=>error(Error('DSP worker failed'));node.onprocessorerror=()=>error(Error('AudioWorklet failed'));
            node.port.onmessage=e=>{
              const m=e.data;if(m.error){error(Error(m.error));return;}
              if(m.flushed)worker.postMessage({command:'flush',...m});
              else worker.postMessage({command:'record',...m},[m.buffer]);
            };
            source=context.createMediaStreamSource(stream);source.connect(node);await context.resume();stop.disabled=false;
            status.textContent=JSON.stringify({phase:'CAPTURING',device:track.label,settings:track.getSettings(),context_rate:context.sampleRate,session_id:session});
          }
          if(m.type==='pcm_ack'){
            if(m.session_id!==session)throw Error('Foreign credit');clearTimeout(timer);q.credit(m);pump();
          }
          if(m.type==='operator_command'&&m.command==='stop')finish();
          if(m.type==='asr'&&m.payload?.type==='ready_to_stop')terminal=true;
          if(m.type==='status'&&m.state==='stopped')status.textContent=JSON.stringify({transport:m.completion,asr:m.experimental_asr,accepted:q.accepted,sent:q.sent,acked:q.acked,terminal,peak_pcm_bytes:q.peak,dsp:dspMetadata},null,2);
        }catch(e){error(e);}
      };
      socket.onerror=()=>error(Error('Socket failure'));
      socket.onclose=()=>{if(!terminal)error(Error('Close before terminal'));else{release();tell('capture_closed');}};
    }catch(e){error(e);}
  };
  stop.onclick=finish;
  fetch('/api/operator/bootstrap',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Authorization unavailable');tell('capture_ready');}).catch(error);
})();
