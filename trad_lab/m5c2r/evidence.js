/* Incremental owner-authenticated evidence. No I/O waits in an audio callback. */
(function(root){'use strict';
const MAX_QUEUE=8*1024*1024,MAX_PACKET=180000,SERVER_SOFT=128*1024*1024;
const rows=[];let queued=0,peak=0,session,auth,sequence=0,active=null,finishPromise=null;
let timer,closing=false,sealed=false,broken=false,failed=false,reason=null,notified=false,serverBytes=0;
const encoder=new TextEncoder();
function fail(phase){
  failed=true;reason??=phase;
  if(!notified){notified=true;queueMicrotask(()=>{try{root.M5C2_EVIDENCE_FAILURE?.(Error(reason));}catch{}});}
}
function item(row){
  const data={...row,perf_ms:row.perf_ms??performance.now(),time_origin:row.time_origin??performance.timeOrigin};
  return {data,size:encoder.encode(JSON.stringify(data)).length};
}
function record(row){
  if(closing||failed)return false;
  try{
    const next=item(row);
    if(next.size>MAX_PACKET){fail('evidence_row_budget');return false;}
    if(queued+next.size>MAX_QUEUE){fail('evidence_queue_budget');return false;}
    rows.push(next);queued+=next.size;peak=Math.max(peak,queued);return true;
  }catch{fail('evidence_serialization');return false;}
}
function binary(kind,buffer,metadata={}){
  if(closing||failed)return false;
  try{
    const input=new Uint8Array(buffer);let text='';
    for(let at=0;at<input.length;at+=8192)text+=String.fromCharCode(...input.subarray(at,at+8192));
    return record({kind,...metadata,b64:btoa(text)});
  }catch{fail('evidence_binary');return false;}
}
function pullDOM(){
  try{
    const observer=root.opener?.M5C2_DOM;if(!observer)return;
    if(observer.failed){fail('operator_evidence_queue_budget');return;}
    for(const row of observer.take()){if(!record(row))break;}
  }catch{fail('operator_evidence_read');}
}
async function sendLoop(){
  while(session&&!sealed&&!broken&&(rows.length||closing)){
    // A reloading Operator briefly has no token. Wait within the unchanged 5 s
    // control budget; never fall back to a revoked owner or retry rejected HTTP.
    const ownerWait=performance.now();let credential;
    try{
      while(!(credential=auth())){
        if(performance.now()-ownerWait>=5000)throw Error('owner');
        await new Promise(resolve=>setTimeout(resolve,50));
      }
    }catch{broken=true;fail('evidence_owner_recovery_timeout');return;}
    const packet=[];let size=0;
    for(const row of rows){if((size+row.size>MAX_PACKET&&packet.length)||packet.length===64)break;packet.push(row.data);size+=row.size;}
    const final=closing&&packet.length===rows.length;
    const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),5000);
    try{
      const response=await fetch('/api/m5c2/evidence',{method:'POST',signal:controller.signal,
        headers:{'content-type':'application/json','x-operator-token':credential},
        body:JSON.stringify({session_id:session,sequence,rows:packet,final,capture_failed:failed})});
      if(!response.ok)throw Error('http');
      const ack=await response.json();
      if(ack.sequence!==sequence||ack.written!==true||ack.final!==final||
         !Number.isSafeInteger(ack.writer_json_bytes)||ack.writer_json_bytes<serverBytes||ack.writer_json_bytes>160*1024*1024)throw Error('ack');
      rows.splice(0,packet.length);queued-=size;sequence++;serverBytes=ack.writer_json_bytes;
      if(final){sealed=true;return;}
      // Preserve the unchanged 160 MiB disk budget, leaving room to drain and seal.
      if(serverBytes>=SERVER_SOFT)fail('evidence_session_budget_stop');
    }catch(error){broken=true;fail(error.name==='AbortError'?'evidence_upload_timeout':'evidence_upload_or_ack_failure');return;}
    finally{clearTimeout(deadline);}
  }
}
function kick(){
  if(active||!session||broken||sealed)return active;
  active=sendLoop().finally(()=>{active=null;});return active;
}
function start(id,authentication){
  if(session){fail('evidence_session_reused');return false;}
  session=id;auth=authentication;
  timer=setInterval(()=>{pullDOM();kick();},50);kick();return true;
}
function stats(){return {queued_bytes:queued,peak_queue_bytes:peak,queue_limit_bytes:MAX_QUEUE,
  packets:sequence,server_json_bytes:serverBytes,failed,reason,sealed,upload_broken:broken};}
function finish(captureFailed=false){
  if(finishPromise)return finishPromise;
  clearInterval(timer);pullDOM();
  if(captureFailed){failed=true;reason??='capture_failed';}
  // Reserve the reason in the next/final packet when the HTTP path is still usable.
  if(failed&&queued<MAX_QUEUE-1024){const last=item({kind:'failure',reason});rows.push(last);queued+=last.size;peak=Math.max(peak,queued);}
  closing=true;
  finishPromise=(async()=>{
    if(!session){broken=true;failed=true;reason??='evidence_no_session';}
    while(session&&!sealed&&!broken){await (active||kick());}
    return {evidence_complete:sealed&&!broken,capture_failed:failed,...stats()};
  })();return finishPromise;
}
root.M5C2Trace={record,binary,start,finish,stats};
})(globalThis);
