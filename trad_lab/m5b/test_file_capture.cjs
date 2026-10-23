'use strict';
const assert=require('node:assert/strict');
const {pcmFromFile}=require('./file_capture.js');
function wav({rate=16000,channels=1,bits=16,format=1}={}){
  const bytes=new ArrayBuffer(48),v=new DataView(bytes),u=new Uint8Array(bytes);
  const text=(at,t)=>[...t].forEach((c,i)=>u[at+i]=c.charCodeAt(0));
  text(0,'RIFF');v.setUint32(4,40,true);text(8,'WAVE');text(12,'fmt ');v.setUint32(16,16,true);
  v.setUint16(20,format,true);v.setUint16(22,channels,true);v.setUint32(24,rate,true);v.setUint16(34,bits,true);
  text(36,'data');v.setUint32(40,4,true);u.set([1,2,3,4],44);return bytes;
}
assert.deepEqual([...new Uint8Array(pcmFromFile(wav(),'ok.wav'))],[1,2,3,4]);
for(const opts of [{rate:48000},{channels:2},{bits:32},{format:3}])assert.throws(()=>pcmFromFile(wav(opts),'bad.wav'));
assert.throws(()=>pcmFromFile(new ArrayBuffer(3),'bad.s16le'));
assert.throws(()=>pcmFromFile(wav().slice(0,46),'truncated.wav'));
const raw=new Uint8Array([0,128,255,127]).buffer;
assert.equal(pcmFromFile(raw,'exact.s16le'),raw);
console.log('PASS: 8 file PCM cases; no resampling or microphone');
