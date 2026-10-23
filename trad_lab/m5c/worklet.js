/* No await, network, disk or resampling in the render callback. Finite 8-batch window. */
class M5CForwarder extends AudioWorkletProcessor{
  constructor(){super();this.batch=new Float32Array(2048);this.used=0;this.sequence=0;this.total=0;this.outstanding=0;this.stopped=false;this.failed=false;
    this.port.onmessage=e=>{
      if(e.data.command==='ack'){
        if(e.data.sequence!==this.sequence-this.outstanding || this.outstanding<=0)return this.failure('worklet_ack_sequence');
        this.outstanding--;
      }else if(e.data.command==='flush' && !this.stopped){
        this.stopped=true;if(this.used)this.sendBatch();
        this.port.postMessage({flushed:true,input_samples:this.total,batches:this.sequence,incomplete:this.failed});
      }
    };
  }
  failure(reason){if(!this.failed)this.port.postMessage({error:reason,input_samples:this.total});this.failed=true;this.stopped=true;}
  sendBatch(){
    if(this.outstanding>=8){this.failure('worklet_backlog_exhausted');return;}
    const buffer=this.batch.slice(0,this.used).buffer;
    this.port.postMessage({sequence:this.sequence++,first_sample:this.total-this.used,samples:this.used,
      channels:1,sample_rate:sampleRate,buffer},[buffer]);this.outstanding++;this.used=0;
  }
  process(inputs){
    if(this.stopped)return true;
    const channels=inputs[0];if(!channels||!channels[0])return true;
    // Node explicitly requests mono. Unexpected channel topology invalidates capture.
    if(channels.length!==1){this.failure('non_mono_worklet_input');return true;}
    const data=channels[0];
    for(let i=0;i<data.length;i++){
      if(!Number.isFinite(data[i])){this.failure('nonfinite_input');return true;}
      this.batch[this.used++]=data[i];this.total++;
      if(this.used===this.batch.length){this.sendBatch();if(this.failed)return true;}
    }
    return true;
  }
}
registerProcessor('m5c-forwarder',M5CForwarder);
