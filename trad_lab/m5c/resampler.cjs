/* Experimental 127-tap Hann-windowed sinc. Original recorder_worker is untouched. */
(function(root){'use strict';
class FIRResampler{
  constructor(rate){
    if(![16000,44100,48000].includes(rate))throw Error('Unsupported measured AudioContext rate');
    this.rate=rate;this.half=63;this.total=0;this.out=0;this.base=0;this.data=[];this.done=false;this.kernels=new Map();
  }
  kernel(rem){
    if(this.kernels.has(rem))return this.kernels.get(rem);
    const fraction=rem/16000,fc=7200/this.rate,k=[];let sum=0;
    for(let j=-this.half;j<=this.half;j++){
      const x=j-fraction;
      const w=Math.abs(x)<=this.half ? .5+.5*Math.cos(Math.PI*x/this.half):0;
      const v=(x===0?2*fc:Math.sin(2*Math.PI*fc*x)/(Math.PI*x))*w;k.push(v);sum+=v;
    }
    for(let i=0;i<k.length;i++)k[i]/=sum;
    this.kernels.set(rem,k);return k;
  }
  push(input){
    if(this.done)throw Error('Input after EOF');
    if(!(input instanceof Float32Array)||input.length>65536)throw Error('Bounded f32 block required');
    for(const x of input){if(!Number.isFinite(x))throw Error('Non-finite sample');this.data.push(x);}
    this.total+=input.length;return this.emit(false);
  }
  emit(eof){
    const result=[];
    while(this.out*this.rate<this.total*16000){
      const position=this.out*this.rate,i=Math.floor(position/16000),rem=position%16000;
      if(this.rate!==16000 && !eof && i+this.half>=this.total)break;
      let value;
      if(this.rate===16000)value=this.data[i-this.base];
      else{
        value=0;const kernel=this.kernel(rem);
        for(let j=-this.half;j<=this.half;j++){
          const at=i+j;if(at>=0 && at<this.total)value+=this.data[at-this.base]*kernel[j+this.half];
        }
      }
      result.push(value);this.out++;
    }
    const keep=Math.max(0,Math.floor(this.out*this.rate/16000)-this.half);
    if(keep>this.base){this.data=this.data.slice(keep-this.base);this.base=keep;}
    return Float32Array.from(result);
  }
  finish(){if(this.done)throw Error('Duplicate EOF');this.done=true;return this.emit(true);}
  metadata(){return {input_samples:this.total,output_samples:this.out,input_rate:this.rate,output_rate:16000,
    taps:127,cutoff_hz:7200,lookahead_samples:this.rate===16000?0:63,
    boundary:'Zero extension only inside finite filter support; output count ceil(N*16000/rate)',
    fractional_last_sample_coverage:this.total*16000%this.rate||this.rate};}
}
function s16(samples){
  const buffer=new ArrayBuffer(samples.length*2),v=new DataView(buffer);
  for(let i=0;i<samples.length;i++){const x=Math.max(-1,Math.min(1,samples[i]));v.setInt16(i*2,x<0?x*32768:x*32767,true);}return buffer;
}
const api={FIRResampler,s16};if(typeof module!=='undefined')module.exports=api;else root.M5CFIR=api;
})(globalThis);
