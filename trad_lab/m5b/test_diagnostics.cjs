'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/diagnostics.js','utf8');
function fixture(operator=true){
  const events={},main={children:[],prepend(n){this.children.unshift(n);}},option={disabled:false};let native=0,consumed=0;
  const element=()=>({children:[],textContent:'',append(...children){this.children.push(...children);},set innerHTML(v){throw Error('unsafe HTML');}});
  const context={navigator:{mediaDevices:{getUserMedia(){native++;return Promise.resolve();}}},
    addEventListener(type,fn){events[type]=fn;},document:{createElement:element,querySelector(s){return s==='main'?main:option;}}};
  if(operator)context.OperatorUI={consumeHistory(){consumed++;}};
  vm.createContext(context);vm.runInContext(source,context);events.DOMContentLoaded();
  return {context,main,option,native:()=>native,consumed:()=>consumed};
}
(async()=>{
  const f=fixture();await assert.rejects(f.context.navigator.mediaDevices.getUserMedia({audio:true}),/deshabilitado/);assert.equal(f.native(),0);
  f.context.OperatorUI.consumeHistory({experimental_asr:{backend:'turbo',transport_completion:'complete',transcription_completion:'unconfirmed_tail',
    unconfirmed_eof_tail:[{text:' <aldosterone>'}],known_errors:['140 over 19']}});
  const panel=f.main.children[0];assert.match(panel.children[1].textContent,/complete.*unconfirmed_tail/);
  assert.match(panel.children[1].textContent,/Backend: turbo/);
  assert.match(panel.children[2].textContent,/<aldosterone>/);assert.equal(f.consumed(),1);assert.equal(f.option.disabled,true);
  f.context.OperatorUI.consumeHistory({experimental_asr:{unconfirmed_eof_tail:[]}});
  assert.doesNotMatch(panel.children[2].textContent,/aldosterone/);
  f.context.OperatorUI.consumeHistory({experimental_asr:{eof_observed:false,error_category:'upstream_send_timeout',transport:{
    sent_bytes:64000,acked_bytes:0,received_confirmed_words:9,delivered_confirmed_words:0,pending_confirmed_words:9}}});
  assert.match(panel.children[1].textContent,/upstream_send_timeout.*64000\/0.*9\/0.*Pendientes de entrega: 9/);
  assert.match(panel.children[2].textContent,/EOF no recibido/);
  assert.doesNotThrow(()=>fixture(false));
  console.log('PASS: native microphone blocked; recovered EOF text safe/visible; next session resets; file popup has no OperatorUI dependency');
})().catch(e=>{console.error(e);process.exitCode=1;});
