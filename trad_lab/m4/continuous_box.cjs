// Laboratory prototype only. Fixed 48 kHz -> 16 kHz, with phase carried across
// blocks. Same 3-sample box average, no filter/AGC/device change. Not used LIVE.
class ContinuousBox48to16 {
  constructor(){this.sum=0;this.count=0;this.input=0;this.output=0;}
  push(block){
    const values=[];
    for(const value of block){
      this.sum+=value;this.count++;this.input++;
      if(this.count===3){values.push(this.sum/3);this.sum=0;this.count=0;this.output++;}
    }
    return Float32Array.from(values);
  }
  finish(){return {input_samples:this.input,output_samples:this.output,trailing_input_samples_unemitted:this.count};}
}
module.exports={ContinuousBox48to16};
