'use strict';
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const elements=[],posts=[];let hidden=true,owns=true,loaded;
const direction={},ui={token:'fake-token',ready:Promise.resolve(),render:()=>{}};
const ctx={OperatorUI:ui,document:{getElementById:()=>direction,createElement:()=>{const e={};elements.push(e);return e;},body:{prepend:()=>{}}},
  addEventListener:(kind,f)=>loaded=f,
  fetch:async(url,opts={})=>{
    if(opts.method==='POST'){const data=JSON.parse(opts.body);posts.push(data);hidden=data.hidden;return {ok:true,json:async()=>({hidden})};}
    return {ok:true,json:async()=>url==='/api/operator/status'?{owns_session:owns,session_id:'s',visual_generation:1}:{hidden}};
  }};
vm.runInNewContext(fs.readFileSync(__dirname+'/controls.js','utf8'),ctx);loaded();
(async()=>{
  await ui.ready;await new Promise(r=>setImmediate(r));assert.equal(ui.directionId,'en-es');assert.equal(ui.canSelectDirection(),false);
  assert(elements[2].textContent.startsWith('OCULTO'));
  await elements[0].onclick();assert.equal(posts[0].hidden,true); // Hide never toggles into reveal.
  await elements[1].onclick();assert.equal(posts[1].hidden,false);
  owns=false;await elements[0].onclick();assert.equal(posts.length,2);
  console.log('PASS: 6 explicit hide/resume/recovery-state and fixed-direction controls');
})().catch(e=>{console.error(e);process.exitCode=1;});
