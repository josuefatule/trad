/* Replay exactly the recorded f32 blocks through the unmodified worker and
 * the candidate, without a microphone, GPU, service or reference transcript. */
const fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const {ContinuousBox,s16}=require('./resampler.cjs');
const [,,input,metadata,worker,out]=process.argv;
const rows=fs.readFileSync(metadata,'utf8').trim().split('\n').map(JSON.parse).filter(r=>r.kind==='pre');
if(!rows.length)throw Error('No pre-resample blocks');
const rate=rows[0].sample_rate, box=new ContinuousBox(rate), source=fs.readFileSync(input);
const a=[],b=[]; let offset=0;
const ctx={self:{postMessage:m=>{if(m.buffer)a.push(Buffer.from(m.buffer));}},Float32Array,ArrayBuffer,DataView,Math};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(worker,'utf8'),ctx);
ctx.self.onmessage({data:{command:'init',config:{sampleRate:rate,targetSampleRate:16000}}});
for(let i=0;i<rows.length;i++) {
  const r=rows[i];if(r.seq!==i || r.sample_rate!==rate)throw Error('Discontinuous capture');
  const bytes=r.samples*4, raw=source.subarray(offset,offset+bytes);if(raw.length!==bytes)throw Error('Truncated input');
  const f=new Float32Array(Uint8Array.from(raw).buffer);offset+=bytes;
  ctx.self.onmessage({data:{command:'record',buffer:f.buffer}});b.push(s16(box.push(f)));
}
if(offset!==source.length)throw Error('Extra input');
const tail=box.finish();b.push(s16(tail.tail));
const original=Buffer.concat(a),candidate=Buffer.concat(b);
fs.writeFileSync(out+'.original.s16le',original,{flag:'wx'});fs.writeFileSync(out+'.candidate.s16le',candidate,{flag:'wx'});
const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
fs.writeFileSync(out+'.json',JSON.stringify({input_sha256:hash(source),worker_sha256:hash(fs.readFileSync(worker)),rate,
  inputs:source.length/4,original_samples:original.length/2,candidate_samples:candidate.length/2,
  original_sha256:hash(original),candidate_sha256:hash(candidate),eof_coverage:tail.coverage,
  caution:'Same capture, deterministic DSP replay only; no ASR quality conclusion.'},null,2),{flag:'wx'});
