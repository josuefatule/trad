"use strict";
addEventListener('DOMContentLoaded',()=>{
  const direction=document.getElementById('direction');
  if(direction){direction.value='en-es';direction.disabled=true;}
  const ui=globalThis.OperatorUI;
  if(ui){ui.directionId='en-es';ui.canSelectDirection=()=>false;ui.render();}
  const hide=document.createElement('button');hide.textContent='OCULTAR subtítulos';
  const resume=document.createElement('button');resume.textContent='REANUDAR: solo resultados nuevos';
  const state=document.createElement('span');state.textContent='Estado de ocultación no medido';document.body.prepend(hide,resume,state);
  const display=hidden=>{state.textContent=hidden?'OCULTO; ASR y registro continúan':'VISIBLE: solo nuevos resultados';};
  ui?.ready.then(async()=>{
    try{const response=await fetch('/api/m5c/presentation',{headers:{'x-operator-token':ui.token}});if(response.ok)display((await response.json()).hidden);}catch{}
  });
  async function command(hidden){
    try{
      const headers={'x-operator-token':ui.token,'Content-Type':'application/json'};
      const status=await (await fetch('/api/operator/status',{headers})).json();
      if(!status.owns_session)throw Error('Solo propietario');
      const result=await fetch('/api/m5c/presentation',{method:'POST',headers,
        body:JSON.stringify({session_id:status.session_id,visual_generation:status.visual_generation,hidden})});
      if(!result.ok)throw Error('Control rechazado; actualizar estado');
      display(hidden);
    }catch(e){state.textContent=e.message;}
  }
  hide.onclick=()=>command(true);resume.onclick=()=>command(false);
});
