// Full-content synthetic A/B. Only resample() changes inside the isolated VM.
const fs=require('fs'),vm=require('vm'),path=require('path'),crypto=require('crypto');
const {ContinuousBox48to16}=require('./continuous_box.cjs');
const sourcePath=path.resolve(__dirname,'../..','app/static/recorder_worker.js');
const source=fs.readFileSync(sourcePath,'utf8');
const buffer=fs.readFileSync(process.argv[2]);
const input=new Float32Array(buffer.buffer.slice(buffer.byteOffset,buffer.byteOffset+buffer.byteLength));
const rows=[];
for(const profile of ['production','phase_carry']){
  const pieces=[];const context=vm.createContext({Float32Array,ArrayBuffer,DataView,Math,self:{postMessage:m=>{if(m.buffer)pieces.push(Buffer.from(m.buffer));}}});
  vm.runInContext(source,context);
  const candidate=new ContinuousBox48to16();
  if(profile==='phase_carry')context.resample=(block,from,to)=>{
    if(from!==48000 || to!==16000)throw Error('Prototype supports only 48k->16k');
    return candidate.push(block);
  };
  context.self.onmessage({data:{command:'init',config:{sampleRate:48000,targetSampleRate:16000}}});
  const began=process.hrtime.bigint();
  for(let i=0;i<input.length;i+=128)context.self.onmessage({data:{command:'record',buffer:input.subarray(i,i+128)}});
  context.self.onmessage({data:{command:'flush'}});
  const output=Buffer.concat(pieces),wallMs=Number(process.hrtime.bigint()-began)/1e6;
  fs.writeFileSync(process.argv[3]+'.'+profile+'.s16',output);
  rows.push({profile,input_samples:input.length,output_samples:output.length/2,wall_ms:wallMs,
    scope:'Node VM CPU harness; includes record/conversion/post callback; not browser visible latency',
    remaining:profile==='phase_carry'?candidate.finish():null});
}
process.stdout.write(JSON.stringify({source_sha256:crypto.createHash('sha256').update(source).digest('hex'),rows},null,2));
