/* Experimental streaming box integrator. Integer time units avoid phase drift.
 * Extends M4's three-sample mean; no claim of clinical or anti-alias quality.
 * EOF emits a normalized partial cell, with its actual coverage reported. */
'use strict';
class ContinuousBox {
  constructor(from, to=16000) {
    if (![16000,44100,48000].includes(from) || to!==16000) throw Error('Unsupported rate');
    Object.assign(this,{from,to,used:0,sum:0,inputs:0,outputs:0,closed:false});
  }
  push(input) {
    if(this.closed)throw Error('Already finished');
    const out=[];
    for(const value of input) {
      if(!Number.isFinite(value))throw Error('Nonfinite PCM');
      this.inputs++;
      let remaining=this.to;
      while(remaining) {
        const weight=Math.min(remaining,this.from-this.used);
        this.sum+=value*weight;this.used+=weight;remaining-=weight;
        if(this.used===this.from) {
          out.push(this.sum/this.from);this.outputs++;this.sum=0;this.used=0;
        }
      }
    }
    return Float32Array.from(out);
  }
  finish() {
    if(this.closed)throw Error('Duplicate EOF');
    this.closed=true;
    const coverage=this.used/this.from;
    const tail=this.used?Float32Array.of(this.sum/this.used):new Float32Array();
    this.outputs+=tail.length;this.sum=0;this.used=0;
    return {tail,coverage,inputs:this.inputs,outputs:this.outputs};
  }
}
function s16(input) {
  const b=Buffer.alloc(input.length*2);
  input.forEach((v,i)=>{const s=Math.max(-1,Math.min(1,v));b.writeInt16LE(Math.trunc(s*(s<0?32768:32767)),i*2);});
  return b;
}
module.exports={ContinuousBox,s16};
