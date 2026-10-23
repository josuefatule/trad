/* Bounded in-memory capture, flushed to private disk only after terminal/error. */
(function(root){'use strict';
let rows=[],bytes=0,session=null,auth=null,finished=false,failed=false,domTimer;
const MAX=64*1024*1024;
function record(row){
  if(finished)return;
  const item={...row,perf_ms:row.perf_ms??performance.now(),time_origin:row.time_origin??performance.timeOrigin};
  const size=new TextEncoder().encode(JSON.stringify(item)).length;
  if(bytes+size>MAX){failed=true;throw Error('Evidence memory budget exhausted');}
  bytes+=size;rows.push(item);
}
function binary(kind,buffer,metadata={}){
  const input=new Uint8Array(buffer);let text='';
  for(let at=0;at<input.length;at+=8192)text+=String.fromCharCode(...input.subarray(at,at+8192));
  record({kind,...metadata,b64:btoa(text)});
}
function pullDOM(){
  const observer=opener?.M5C2_DOM;if(!observer)return;
  if(observer.failed)throw Error('Operator DOM evidence budget exhausted');
  for(const row of observer.take())record(row);
}
function start(id,authentication){
  if(session)throw Error('Evidence session reused');session=id;auth=authentication;
  domTimer=setInterval(()=>{try{pullDOM();}catch(e){root.M5C2_EVIDENCE_FAILURE?.(e);}},1000);
}
async function finish(captureFailed=false){
  if(finished)return {evidence_complete:!failed,already_finished:true};
  clearInterval(domTimer);pullDOM();finished=true;
  if(!session||!auth)throw Error('No authenticated session for evidence');
  let sequence=0;
  while(rows.length){
    const packet=[];let size=0;
    for(const row of rows){const n=new TextEncoder().encode(JSON.stringify(row)).length;if((size+n>180000&&packet.length)||packet.length===64)break;packet.push(row);size+=n;}
    const final=rows.length===packet.length;
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);
    let response;
    try{response=await fetch('/api/m5c2/evidence',{method:'POST',signal:controller.signal,headers:{'content-type':'application/json','x-operator-token':auth()},
      body:JSON.stringify({session_id:session,sequence,rows:packet,final,capture_failed:captureFailed||failed})});}
    catch(e){failed=true;throw e;}finally{clearTimeout(timer);}
    if(!response.ok){failed=true;throw Error('Evidence upload failed; retain CAPTURE; no automatic retry');}
    const ack=await response.json();if(ack.sequence!==sequence||!ack.written||ack.final!==final){failed=true;throw Error('Evidence ACK mismatch');}rows.splice(0,packet.length);sequence++;
  }
  return {evidence_complete:true,packets:sequence,capture_failed:captureFailed||failed,json_bytes:bytes};
}
root.M5C2Trace={record,binary,start,finish};
})(globalThis);
