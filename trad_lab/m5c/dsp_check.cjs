'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const {FIRResampler,s16}=require('./resampler.cjs');
const out=process.argv[2];fs.mkdirSync(out,{recursive:false});
const result={rates:[],scope:'Signal-only, no ASR or native microphone. FIR future support is delayed, not invented audio.'};
function convert(x,rate,size=2048){const r=new FIRResampler(rate),chunks=[];for(let at=0;at<x.length;at+=size)chunks.push(Buffer.from(s16(r.push(x.slice(at,at+size)))));chunks.push(Buffer.from(s16(r.finish())));return {pcm:Buffer.concat(chunks),metadata:r.metadata()};}
function amplitude(x,rate,f){let a=0,b=0,n=0;for(let i=1600;i<x.length-1600;i++){a+=x[i]*Math.cos(2*Math.PI*f*i/rate);b+=x[i]*Math.sin(2*Math.PI*f*i/rate);n++;}return 2*Math.hypot(a,b)/n;}
for(const rate of [16000,44100,48000]){
  const row={rate,tones:[]};
  for(const f of rate===16000?[1000,6000]:[1000,6000,9000,12000]){
    const x=Float32Array.from({length:rate*2},(_,i)=>.4*Math.sin(2*Math.PI*f*i/rate));
    const {pcm}=convert(x,rate);const y=Int16Array.from(new Int16Array(pcm.buffer,pcm.byteOffset,pcm.length/2));
    const af=f>8000?Math.abs(16000-f):f,amp=amplitude(y,16000,af)/32768;
    const gain=20*Math.log10(Math.max(amp,1e-12)/.4);row.tones.push({input_hz:f,output_probe_hz:af,gain_db:gain});
    if((f<=6000&&Math.abs(gain)>.15)||(f>=9000&&gain> -45))throw Error('Spectral acceptance failed');
  }
  const impulse=new Float32Array(rate);impulse[rate/2]=.5;const i=convert(impulse,rate),values=new Int16Array(i.pcm.buffer,i.pcm.byteOffset,i.pcm.length/2);
  let peak=0;for(let k=0;k<values.length;k++)if(Math.abs(values[k])>Math.abs(values[peak]))peak=k;
  if(Math.abs(peak-8000)>1)throw Error('Impulse phase error');row.impulse_peak_sample=peak;
  const long=convert(new Float32Array(rate*60),rate);if(long.pcm.length!==1920000)throw Error('Duration error');
  row.sixty_second_samples=long.pcm.length/2;row.metadata=long.metadata;result.rates.push(row);
}
const pre='C:/live-captions/logs/trad_lab/m4b_openerfix_20261020T161600Z/environment_opener_ready/copy/logs/trad_lab/physical_03/browser/pre.f32le';
const bytes=fs.readFileSync(pre),input=new Float32Array(bytes.buffer,bytes.byteOffset,bytes.length/4);
const candidate=convert(input,48000,128);fs.writeFileSync(path.join(out,'prefix_fir.s16le'),candidate.pcm);
const chunks=[],worker={Float32Array,ArrayBuffer,DataView,Math,self:{postMessage:m=>{if(m.buffer)chunks.push(Buffer.from(m.buffer));}}};
vm.runInNewContext(fs.readFileSync('C:/live-captions/app/static/recorder_worker.js','utf8'),worker);
worker.self.onmessage({data:{command:'init',config:{sampleRate:48000,targetSampleRate:16000}}});
for(let at=0;at<input.length;at+=128)worker.self.onmessage({data:{command:'record',buffer:input.slice(at,at+128).buffer}});
worker.self.onmessage({data:{command:'flush'}});const original=Buffer.concat(chunks);fs.writeFileSync(path.join(out,'prefix_original.s16le'),original);
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
result.physical_prefix={source:pre,pre_sha256:sha(bytes),input_samples:input.length,metadata:candidate.metadata,
  original:{bytes:original.length,sha256:sha(original)},candidate:{bytes:candidate.pcm.length,sha256:sha(candidate.pcm)},
  caveat:'Incomplete M4-B prefix; metadata currentFrame discontinuities persist. No physical EOF or full acoustic-continuity certification.'};
if(sha(original)!=='ec89c0da00aef65b452e3d65a0c12569fb64106d7c3ba2945140e55e2db30308')throw Error('Original replay differs');
fs.writeFileSync(path.join(out,'signal.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({status:'PASS',rates:result.rates.length,original_bytes:original.length,candidate_bytes:candidate.pcm.length}));
