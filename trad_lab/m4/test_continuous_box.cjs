const assert=require('assert'),{ContinuousBox48to16}=require('./continuous_box.cjs');
// Segmentation invariance on a varying signal is the required property; compare
// against independent averaging of the full stream, not the implementation.
for(const blockSize of [1,2,3,7,128,480,1000]){
  const signal=Float32Array.from({length:48000},(_,i)=>Math.sin(i*.173)+.1*Math.cos(i*.027));
  const resampler=new ContinuousBox48to16(),pieces=[];
  for(let i=0;i<signal.length;i+=blockSize)pieces.push(...resampler.push(signal.subarray(i,i+blockSize)));
  assert.equal(pieces.length,16000);
  for(let i=0;i<16000;i++)assert(Math.abs(pieces[i]-(signal[3*i]+signal[3*i+1]+signal[3*i+2])/3)<1e-7);
  assert.equal(resampler.finish().trailing_input_samples_unemitted,0);
}
const short=new ContinuousBox48to16();short.push(Float32Array.from([.1,.2]));
assert.equal(short.finish().trailing_input_samples_unemitted,2);
console.log('PASS: 7 block partitions, waveform/sample count invariance, explicit incomplete EOF group');
