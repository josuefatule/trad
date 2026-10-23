'use strict';
importScripts('/static/m5c_resampler.js');
let dsp=null,next=0,total=0,failed=false,flushed=false;
onmessage=e=>{
  if(failed)return;
  try{
    const m=e.data;
    if(m.command==='init'){
      if(dsp)throw Error('Worker already initialized');dsp=new M5CFIR.FIRResampler(m.sample_rate);return;
    }
    if(!dsp||flushed)throw Error('Worker state invalid');
    let audio;
    if(m.command==='record'){
      if(m.sequence!==next++ || m.first_sample!==total || m.samples!==m.buffer.byteLength/4 || m.channels!==1 || m.sample_rate!==dsp.rate)throw Error('Worklet continuity invalid');
      total+=m.samples;audio=dsp.push(new Float32Array(m.buffer));
      const buffer=M5CFIR.s16(audio);postMessage({buffer,ack:m.sequence,input_samples:total},[buffer]);
    }else if(m.command==='flush'){
      if(m.incomplete || m.input_samples!==total || m.batches!==next)throw Error('Incomplete worklet flush');
      audio=dsp.finish();flushed=true;const buffer=M5CFIR.s16(audio);
      postMessage({buffer,flushed:true,metadata:dsp.metadata()},[buffer]);
    }else throw Error('Worker command invalid');
  }catch(e){failed=true;postMessage({error:e.message});}
};
