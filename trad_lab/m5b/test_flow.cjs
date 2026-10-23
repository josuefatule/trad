'use strict';
const assert=require('node:assert/strict');
const {FrameCredit,availabilityDelay}=require('./file_capture.js');
(async()=>{
  assert.equal(availabilityDelay('realtime',64000,100,100),2000);
  assert.equal(availabilityDelay('realtime',128000,100,3100),1000);
  assert.equal(availabilityDelay('realtime',128000,100,5100),0);
  assert.equal(availabilityDelay('accelerated',64000,100,100),0);
  assert.throws(()=>availabilityDelay('unknown',64000,0,0));
  const gate=new FrameCredit(.1),sha='exact-block-hash';
  gate.submit(64000,sha);
  assert.throws(()=>gate.submit(64000,sha),/sin crédito/);
  let advanced=false;const waiting=gate.wait().then(()=>{advanced=true;});
  await new Promise(r=>setTimeout(r,5));assert.equal(advanced,false);
  for(const bad of [{frame_sequence:1,bytes:64000,received_bytes:64000,sha256:sha},
    {frame_sequence:0,bytes:64000,received_bytes:64000,sha256:'bad'}])assert.throws(()=>gate.accept(bad));
  gate.accept({frame_sequence:0,bytes:64000,received_bytes:64000,sha256:sha});await waiting;
  assert.equal(gate.acked,64000);assert.equal(gate.pending,null);
  assert.throws(()=>gate.accept({frame_sequence:0,bytes:64000,received_bytes:64000,sha256:sha}));
  gate.submit(1234,sha);assert.equal(gate.sent,65234);
  gate.accept({frame_sequence:1,bytes:1234,received_bytes:65234,sha256:sha});await gate.wait();
  const timeout=new FrameCredit(.005);timeout.submit(2,'two');
  await assert.rejects(timeout.wait(),/sesión incompleta/);assert.equal(timeout.acked,0);
  const failed=new FrameCredit(1);failed.submit(2,'two');const stopped=failed.wait();failed.fail(Error('closed'));
  await assert.rejects(stopped,/closed/);assert.equal(failed.acked,0);
  console.log('PASS: real-time availability, explicit acceleration, one frame credit, SHA/order/duplicate rejection, timeout and disconnection');
})().catch(e=>{console.error(e);process.exitCode=1;});
