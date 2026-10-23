'use strict';
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
async function check(ok=true){
  const requests=[];let timerId=0;
  const ctx={TextEncoder,Uint8Array,AbortController,performance:{now:()=>42,timeOrigin:1000},opener:{},btoa:s=>Buffer.from(s,'binary').toString('base64'),
    setInterval:()=>++timerId,clearInterval:()=>{},setTimeout,clearTimeout,
    fetch:async(url,options)=>{const m=JSON.parse(options.body);requests.push(m);assert.equal(options.headers['x-operator-token'],'test-owner');return {ok,json:async()=>({sequence:m.sequence,written:true,final:m.final})};}};
  vm.runInNewContext(fs.readFileSync(__dirname+'/evidence.js','utf8'),ctx);
  const t=ctx.M5C2Trace;t.start('s',()=> 'test-owner');
  const samples=new Float32Array(2048);t.binary('pre',samples.buffer,{sequence:0,channels:1,sample_rate:48000});
  t.record({kind:'dom',perf_ms:11,time_origin:2000,panel:'partial',text:'57'});t.binary('sent',new ArrayBuffer(0),{sequence:0,eof:true});
  if(!ok){await assert.rejects(t.finish(),/upload failed/);assert.equal(requests.length,1);return;}
  const result=await t.finish();assert(result.evidence_complete);assert.equal(requests.length,1);assert(requests[0].final);
  const rows=requests[0].rows;assert.equal(Buffer.from(rows[0].b64,'base64').length,8192);assert.equal(rows[1].perf_ms,11);assert.equal(rows[1].time_origin,2000);assert.equal(rows[2].b64,'');
  assert.equal((await t.finish()).already_finished,true);
}
(async()=>{await check();await check(false);console.log('PASS: evidence bytes, clocks, final ACK, no retry on HTTP error, bounded page capture');})().catch(e=>{console.error(e);process.exitCode=1;});
