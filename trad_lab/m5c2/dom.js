'use strict';
addEventListener('DOMContentLoaded',()=>{
  let rows=[],bytes=0;const api={failed:false,take:()=>{const result=rows;rows=[];bytes=0;return result;}};globalThis.M5C2_DOM=api;
  const add=(kind,data)=>{const row={kind,...data,perf_ms:performance.now(),time_origin:performance.timeOrigin,visibility:document.visibilityState};const size=JSON.stringify(row).length*2;if(bytes+size>2*1024*1024){api.failed=true;return;}bytes+=size;rows.push(row);};
  for(const id of ['partial','confirmed','pending','ready']){
    const element=document.getElementById(id);if(!element)continue;
    new MutationObserver(()=>{const text=element.textContent;if(text.length>40000){api.failed=true;return;}add('dom',{panel:id,text});}).observe(element,{childList:true,subtree:true,characterData:true});
  }
  for(const id of ['start','stop','clear'])document.getElementById(id)?.addEventListener('click',()=>add('control',{action:id}));
});
