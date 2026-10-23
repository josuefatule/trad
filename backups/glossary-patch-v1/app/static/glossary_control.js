"use strict";
(() => {
  const ui=globalThis.OperatorUI, select=document.getElementById("glossary-mode"), info=document.getElementById("glossary-info");
  if(!ui || !select || !info)return;
  let busy=false, errorMessage="";
  const render=ui.render.bind(ui);
  ui.render=function(){
    render();
    const state=ui.snapshot?.glossary;
    select.disabled=busy || !state || !ui.authorized || ui.localActive || ui.snapshot?.can_change_glossary!==true || !!state.forced_by_environment;
    if(!state)return;
    select.value=state.mode;
    const label={soft:"Activo para pruebas",shadow:"Observación: conserva el comportamiento anterior",off:"Comportamiento anterior"}[state.effective_mode];
    info.textContent=errorMessage || state.error || `${label} · ${state.concepts} conceptos${state.version?" · "+state.version:""}`;
    const normal=document.getElementById("normalization-info");
    if(normal && state.effective_mode!=="off")normal.textContent=ui.directionId==="en-es"?
      `Glosario médico · ${state.concepts} conceptos · ${state.effective_mode==="soft"?"corrección conservadora":"observación"}`:
      `Glosario médico bilingüe · ${state.concepts} conceptos · normalización española anterior`;
  };
  select.addEventListener("change",async()=>{
    if(select.disabled)return;
    const mode=select.value, generation=ui.snapshot?.glossary?.generation;
    busy=true;errorMessage="";ui.render();
    try{
      const response=await fetch("/api/operator/glossary",{method:"POST",headers:{"Content-Type":"application/json","X-Operator-Token":ui.token},body:JSON.stringify({mode,generation})});
      if(!response.ok)throw Error("No se pudo cambiar el glosario. Detén la sesión y actualiza la consola.");
      await ui.refresh();
    }catch(error){errorMessage=error.message;}
    finally{busy=false;ui.render();}
  });
  ui.ready.then(()=>ui.render());
})();
