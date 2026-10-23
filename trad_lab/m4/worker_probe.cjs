// Execute the existing worker in a VM; never edit the operational source.
const fs=require('fs'),vm=require('vm'),crypto=require('crypto'),path=require('path');
const filename=path.resolve(__dirname,'../..','app/static/recorder_worker.js');
const source=fs.readFileSync(filename,'utf8');
function run(blockSize,seconds){
  let samples=0,frames=0;
  const context=vm.createContext({Float32Array,ArrayBuffer,DataView,Math,self:{postMessage:m=>{
    if(m.buffer){samples+=m.buffer.byteLength/2;frames++;}
  }}});
  vm.runInContext(source,context,{filename});
  context.self.onmessage({data:{command:'init',config:{sampleRate:48000,targetSampleRate:16000}}});
  const inputCount=48000*seconds;
  for(let offset=0;offset<inputCount;offset+=blockSize){
    const input=new Float32Array(Math.min(blockSize,inputCount-offset)).fill(.1);
    context.self.onmessage({data:{command:'record',buffer:input}});
  }
  context.self.onmessage({data:{command:'flush'}});
  return {input_samples:inputCount,block_size:blockSize,frames,output_samples:samples,expected_samples:16000*seconds,
    output_duration_s:samples/16000,excess_samples:samples-16000*seconds};
}
process.stdout.write(JSON.stringify({worker_path:filename,sha256:crypto.createHash('sha256').update(source).digest('hex'),
  experiments:[run(128,60),run(480,60),run(960,60)],
  interpretation:'Block length is the only changed variable; constant signal isolates sample-count behavior. This does not measure microphone quality or ASR accuracy.'},null,2));
