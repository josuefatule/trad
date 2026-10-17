"use strict";
(async () => {
  const ui = globalThis.OperatorUI;
  if (!await ui.ready) return;
  let stopped = false;
  const update = async () => {
    if(stopped)return;
    await ui.refresh();
    if(!stopped)setTimeout(update, ui.config.poll_seconds*1000);
  };
  const elapsed = () => {
    if(stopped)return;
    const seconds = ui.startedAt ? Math.floor((Date.now()-ui.startedAt)/1000) : 0;
    if(ui.localActive)document.getElementById("elapsed").textContent=
      `${Math.floor(seconds/60).toString().padStart(2,"0")}:${(seconds%60).toString().padStart(2,"0")}`;
    if(!stopped)setTimeout(elapsed,1000);
  };
  const microphone=document.getElementById("microphone");
  const selected=()=>{document.getElementById("selected-microphone").textContent=microphone.selectedOptions?.[0]?.textContent || "Predeterminado";};
  microphone.addEventListener("change",selected);selected();
  const available=await fetch("/overlay",{cache:"no-store"}).catch(()=>null);
  document.getElementById("overlay-availability").textContent=available?.ok?"Overlay page: available (OBS not verified)":"Overlay page: unavailable";
  window.addEventListener("beforeunload",()=>{stopped=true;});
  update();elapsed();
})();
