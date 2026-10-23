"use strict";
// Loaded only by the laboratory copy, before any operational UI script.
if (navigator.mediaDevices) Object.defineProperty(navigator.mediaDevices,"getUserMedia",{
  value:()=>Promise.reject(Error("M5-B: micrófono deshabilitado; ensayo exclusivamente con PCM de archivo")),configurable:false,writable:false
});
addEventListener("DOMContentLoaded",()=>{
  if(!globalThis.OperatorUI)return;
  const panel=document.createElement("section");panel.id="m5b-diagnostics";
  const title=document.createElement("h2");title.textContent="M5-B experimental · PCM de archivo · DeepL OFF";
  const status=document.createElement("p"),tail=document.createElement("pre"),alerts=document.createElement("pre");tail.id="m5b-eof-tail";
  panel.append(title,status,tail,alerts);document.querySelector("main").prepend(panel);
  const original=globalThis.OperatorUI.consumeHistory;
  globalThis.OperatorUI.consumeHistory=function(data){
    original.call(this,data);
    const diagnostic=data.experimental_asr || {};
    status.textContent=`Backend: ${diagnostic.backend || "sin sesión"} · Transporte: ${diagnostic.transport_completion || "sin sesión"} · Transcripción: ${diagnostic.transcription_completion || "sin sesión"}`;
    if(diagnostic.error_category)status.textContent+=` · Fallo: ${diagnostic.error_category}`;
    if(diagnostic.transport){const t=diagnostic.transport;status.textContent+=` · PCM enviado/ACK: ${t.sent_bytes}/${t.acked_bytes} bytes · Confirmadas recibidas/entregadas: ${t.received_confirmed_words}/${t.delivered_confirmed_words} · Pendientes de entrega: ${t.pending_confirmed_words}`;}
    tail.textContent="COLA EOF NO CONFIRMADA (no READY): "+(diagnostic.unconfirmed_eof_tail || []).map(w=>w.text).join("");
    if(diagnostic.eof_observed===false)tail.textContent="EOF no recibido: cola final todavía no evaluada. El contenido provisional no se convierte en confirmado.";
    alerts.textContent="Riesgos conocidos del candidato, sin corrección automática ni diagnóstico de esta sesión:\n"+(diagnostic.known_errors || []).join("\n");
  };
  const direction=document.querySelector('#direction option[value="es-en"]');if(direction)direction.disabled=true;
});
