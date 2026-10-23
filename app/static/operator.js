"use strict";
const $ = (id) => document.getElementById(id);
const ui = new OperatorConsole.ConsoleView($);
globalThis.OperatorUI = ui;
let active = null;
let captureWindow=null,monitor=null;
let captureDeviceId=null,preferredInput=null;
try {
  const saved=JSON.parse(localStorage.getItem("trad-audio-input-v1"));
  if(typeof saved?.deviceId==="string" && saved.deviceId && typeof saved.label==="string")preferredInput=saved;
} catch {}
const historyPanels=["partial","confirmed","segments","pending","ready","normalized","normalized-segments","english","english-segments","corrections"];
function newHistory(sessionId=null) {
  return {readyIds:new Set(),normalizedSegments:[],translatedSegments:[],translationResults:new Map(),nextTranslationSequence:1,sessionId,truncated:0};
}
function boundHistory(s) {
  const limit=ui.snapshot?.operator_history?.ui_history_segments || 500;
  let removed=0;
  for(const parts of [s.normalizedSegments,s.translatedSegments])if(parts && parts.length>limit){s.truncated=(s.truncated || 0)+parts.length-limit;parts.splice(0,parts.length-limit);}
  for(const parts of [s.normalizedSegments,s.translatedSegments])if(parts){
    let characters=parts.reduce((sum,text)=>sum+text.length,0);
    while(parts.length>1 && characters>60000){const first=parts.shift();characters-=first.length;removed+=first.length;s.truncated=(s.truncated || 0)+1;}
    if(parts.length===1 && characters>60000){removed+=characters-60000;parts[0]=parts[0].slice(-60000);}
  }
  if(s.normalizedSegments)flow("normalized",compactNormalizedText(s.normalizedSegments));
  if(s.translatedSegments)flow("english",compactNormalizedText(s.translatedSegments));
  while(s.readyIds?.size>limit)s.readyIds.delete(s.readyIds.values().next().value);
  for(const id of ["ready","normalized-segments","english-segments","corrections","confirmed","segments","partial"]){
    const element=$(id);if(element.textContent.length>60000){removed+=element.textContent.length-60000;element.textContent=element.textContent.slice(-60000);}
  }
  s.truncatedCharacters=(s.truncatedCharacters || 0)+removed;
  if(s.truncated || s.truncatedCharacters)$("control-notice").textContent=`Historial visual limitado: ${s.truncated || 0} entradas y ${s.truncatedCharacters || 0} caracteres retirados; no afecta captions ni pipeline.`;
}
ui.consumeHistory=data=>{
  const history=data.operator_history;if(!history)return;
  const resync=monitor?.sessionId!==data.session_id || history.history_gap;
  if(resync){
    monitor=newHistory(data.session_id);monitor.nextTranslationSequence=history.first_translation_sequence;
    for(const id of historyPanels)$(id).textContent="";
    ui.historyCursor=0;
  }
  if(!monitor)monitor=newHistory(data.session_id);
  monitor.translationStatus=history.config?.translation_status;
  for(const entry of history.events || [])if(entry.journal_id>ui.historyCursor){
    const message=entry.message;
    if(message.type==="segmentation")renderSegmentation(monitor,message.segmentation,message.normalization);
    if(message.type==="translation"){
      if(resync && message.translation.sequence>monitor.nextTranslationSequence){
        debug(`recovery history gap before sequence ${message.translation.sequence}`);
        monitor.nextTranslationSequence=message.translation.sequence;
      }
      renderTranslation(monitor,message);
    }
    ui.historyCursor=entry.journal_id;
  }
  ui.historyCursor=history.cursor;
  if(history.transcript){$("partial").textContent=history.transcript.partial_text;flow("confirmed",history.transcript.confirmed_text);}
  $("pending").textContent=history.pending_segment || "";
  boundHistory(monitor);
  if(history.truncated_events)$("control-notice").textContent=`Historial de recuperación: ${history.truncated_events} eventos antiguos retirados por límite de memoria.`;
};
function flow(id, text) {
  const element=$(id), following=element.scrollHeight===undefined || element.scrollHeight-element.clientHeight-element.scrollTop<40;
  element.textContent=text;
  if(following)element.scrollTop=element.scrollHeight;
}
function renderSegmentation(s, result, normalization) {
  if (!result) return;
  $("pending").textContent = result.pending_segment;
  const stamp = value => value == null ? "?" : `${Math.floor(value / 60).toString().padStart(2, "0")}:${(value % 60).toFixed(2).padStart(5, "0")}`;
  const normalizedById = new Map((normalization?.segments || []).map(item => [item.segment_id, item]));
  for (const segment of result.ready_segments) {
    if (s.readyIds.has(segment.id)) continue;
    const item = normalizedById.get(segment.id);
    if (!item) throw new Error("El backend no envió el texto normalizado. Reinicia FastAPI y recarga esta página.");
    s.readyIds.add(segment.id);
    $("ready").textContent += `[${segment.id}] [${stamp(segment.start_time)} → ${stamp(segment.end_time)}] ${segment.reason} · ${segment.word_count} palabras · ${Math.round(segment.latency_ms)} ms\n${segment.text}\n\n`;
    s.normalizedSegments.push(item.normalized_text);
    flow("normalized", compactNormalizedText(s.normalizedSegments));
    $("normalized-segments").textContent += `[${segment.id}]\n${item.normalized_text}\n\n`;
    for (const correction of item?.corrections || []) {
      const visible = value => !value || /^\s*$/.test(value) ? JSON.stringify(value) : value;
      $("corrections").textContent += `${visible(correction.source)} → ${visible(correction.replacement)}\nconfidence: ${correction.confidence.toFixed(3)}\nrule: ${correction.rule}\nsegment: ${segment.id}\n\n`;
    }
    for (const suggestion of item?.suggestions || []) {
      $("corrections").textContent += `SUGGESTION${suggestion.cross_segment ? " · CROSS SEGMENT" : ""}\nsource: ${suggestion.source}\ncandidate: ${suggestion.candidate}\nconfidence: ${suggestion.confidence.toFixed(3)}\nrule: ${suggestion.rule}\nsegment: ${segment.id}\n\n`;
    }
  }
  for (const event of result.events || []) {
    if (event.type === "late_revision_detected") debug(`late_revision_detected ${JSON.stringify(event)}`);
  }
  boundHistory(s);
}
function compactNormalizedText(parts) {
  let compact = "";
  for (const part of parts) {
    const clean = String(part || "").replace(/\s+/g, " ").trim();
    if (!clean) continue;
    const separator = compact && !/^[,.;:!?]/.test(clean) ? " " : "";
    compact += separator + clean;
  }
  return compact;
}
function translationStatus(status, queueDepth) {
  const state = status?.state || "unknown";
  const provider = status?.provider ? ` (${status.provider})` : "";
  if(!ui.lastTranslationFailed)ui.translator(status);
  $("translation-status").textContent = [
    `provider: ${status?.provider || "none"}`,
    `status: ${state}`,
    `queue depth: ${queueDepth ?? "—"}`,
    status?.message ? `detail: ${status.message}` : "",
  ].filter(Boolean).join("\n");
}
function renderTranslation(s, data) {
  if (data.session_id !== s.sessionId) {
    debug(`translation discarded for stale session ${data.session_id}`);
    return;
  }
  const result = data.translation;
  if (result.sequence < s.nextTranslationSequence) return;
  s.translationResults.set(result.sequence, result);
  while (s.translationResults.has(s.nextTranslationSequence)) {
    const ready = s.translationResults.get(s.nextTranslationSequence);
    s.translationResults.delete(s.nextTranslationSequence++);
    if (ready.success) {
      s.translatedSegments.push(ready.translated_text);
      flow("english", compactNormalizedText(s.translatedSegments));
      if(ui.lastTranslationFailed)$("error").textContent="";
      ui.lastTranslationFailed=false;
      ui.translator({state:"ready",provider:ready.provider}, true);
    } else {
      ui.lastTranslationFailed=true;
      ui.translator({state:"error",provider:ready.provider});
      ui.error(ready.error);
    }
    $("english-segments").textContent += `[${ready.segment_id}] #${ready.sequence} ${ready.provider} ${ready.success?"OK":"ERROR"}\n${ready.success?ready.translated_text:OperatorConsole.userError(ready.error)}\n\n`;
    $("translation-status").textContent = [
      `provider: ${ready.provider}`,
      `status: ${ready.success ? "completed" : "error"}`,
      `segment: ${ready.segment_id} (#${ready.sequence})`,
      `translation latency: ${OperatorConsole.ms(ready.latency_ms)}`,
      `queue delay: ${OperatorConsole.ms(ready.queue_delay_ms)}`,
      `queue depth: ${data.translation_queue_depth ?? "—"}`,
      `attempts: ${ready.attempt_count}`,
      ready.error ? `error: ${OperatorConsole.userError(ready.error)}` : "",
    ].filter(Boolean).join("\n");
  }
  boundHistory(s);
}
function debug(message) {
  $("debug").textContent = `${new Date().toISOString()} ${message}\n` +
    $("debug").textContent.split("\n").slice(0, 99).join("\n");
}
function controls(busy) {
  ui.localActive=busy;ui.render();
}
async function microphones(permission = false) {
  if (permission) {
    const temporary = await navigator.mediaDevices.getUserMedia({audio: true});
    temporary.getTracks().forEach(track => track.stop());
  }
  const selected = $("microphone").value || preferredInput?.deviceId || "";
  const devices = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === "audioinput");
  const missing=selected && !devices.some(d=>d.deviceId===selected);
  $("microphone").replaceChildren(new Option("Predeterminado", ""),
    ...devices.map((d, i) => new Option(d.label || `Micrófono ${i + 1}`, d.deviceId)),
    ...(missing?[new Option(`${preferredInput?.label || "Entrada seleccionada"} · no disponible`,selected)]:[]));
  $("microphone").value = selected;
  $("selected-microphone").textContent=$("microphone").selectedOptions?.[0]?.textContent || "Predeterminado";
}
$("microphone").onchange=()=>{
  if(ui.localActive)return;
  const deviceId=$("microphone").value;
  preferredInput=deviceId?{deviceId,label:$("microphone").selectedOptions?.[0]?.textContent || "Entrada de audio"}:null;
  try {
    if(preferredInput)localStorage.setItem("trad-audio-input-v1",JSON.stringify(preferredInput));
    else localStorage.removeItem("trad-audio-input-v1");
  } catch {}
  $("selected-microphone").textContent=$("microphone").selectedOptions?.[0]?.textContent || "Predeterminado";
};
navigator.mediaDevices.addEventListener?.("devicechange",()=>{
  if(!ui.localActive && !active)microphones().catch(error=>ui.error(error));
});
async function release(s) {
  if (s.releasing) return s.releasing;
  s.releasing = (async () => {
    s.stream?.getTracks().forEach(track => track.stop());
    s.source?.disconnect();
    s.worklet?.disconnect();
    s.worker?.terminate();
    if (s.context && s.context.state !== "closed") await s.context.close();
  })();
  return s.releasing;
}
async function fail(s, error) {
  if (active !== s) return;
  clearTimeout(s.timer);
  s.failed = true;
  ui.error(error);
  ui.phaseTo("ERROR");
  $("connection").textContent = "Error / Disconnected";
  debug($("error").textContent);
  s.socket?.close();
  await release(s);
  if(ui.captureMode)window.opener?.postMessage({type:"capture_failed"},location.origin);
  if (active === s) { active = null; controls(false); }
  $("capture").textContent = "Micrófono inactivo";
}
function send(s, buffer) {
  if (s.socket.readyState !== WebSocket.OPEN) throw new Error("Se perdió la conexión durante la captura");
  if (s.socket.bufferedAmount > 1_048_576) throw new Error("Audio acumulado: conexión demasiado lenta. Reinicia la sesión.");
  s.socket.send(buffer);
}
async function capture(s) {
  if (active !== s) return;
  await s.context.audioWorklet.addModule("/static/pcm_worklet.js");
  if (active !== s) return;
  s.worker = new Worker("/static/recorder_worker.js");
  s.worker.postMessage({command: "init", config: {sampleRate: s.context.sampleRate, targetSampleRate: 16000}});
  s.worker.onerror = () => fail(s, new Error("Error en la conversión PCM"));
  s.worklet = new AudioWorkletNode(s.context, "pcm-forwarder", {
    numberOfInputs: 1, numberOfOutputs: 0, channelCount: 1,
  });
  s.worklet.onprocessorerror = () => fail(s, new Error("Error del AudioWorklet"));
  s.worker.onmessage = event => {
    if (active !== s) return;
    try {
      if (event.data.flushed) {
        send(s, new ArrayBuffer(0));
        debug("audio EOF enviado; esperando ready_to_stop");
        release(s);
      } else send(s, event.data.buffer);
    } catch (error) { fail(s, error); }
  };
  s.worklet.port.onmessage = event => {
    if (active !== s) return;
    if (event.data.flushed) s.worker.postMessage({command: "flush"});
    else {
      const buffer = event.data.buffer;
      s.worker.postMessage({command: "record", buffer}, [buffer]);
    }
  };
  s.source = s.context.createMediaStreamSource(s.stream);
  s.source.connect(s.worklet);
  await s.context.resume();
  if (active !== s) return;
  $("capture").textContent = `${s.stream.getAudioTracks()[0].label} | ${s.context.sampleRate} Hz → PCM s16le mono 16000 Hz`;
  $("selected-microphone").textContent=s.stream.getAudioTracks()[0].label;
  $("stop").disabled = false;
  ui.phaseTo("LIVE");
  debug("audio stream started");
}
$("refresh").onclick = () => microphones(true).catch(error => ui.error(error));
$("clear").onclick = () => ui.clear();
$("recover-owner").onclick=async()=>{const input=$("recovery-code");const code=input.value;input.value="";await ui.command("recover",{admin_code:code});};
$("rearm-translator").onclick=()=>ui.command("translator-reset");
$("acknowledge-stop").onclick=()=>ui.command("acknowledge-stop");
$("direction").onchange=()=>{
  if(ui.canSelectDirection() && ["en-es","es-en"].includes($("direction").value))ui.directionId=$("direction").value;
  ui.render();
};
$("start").onclick = async () => {
  if(active || !await ui.ready || $("start").disabled)return;
  if(ui.recovery && !ui.captureMode){
    if(captureWindow && !captureWindow.closed){$("error").textContent="Cierra la ventana de captura anterior antes de iniciar otra sesión.";return;}
    captureWindow=window.open("/capture","_blank","popup,width=620,height=420");
    if(!captureWindow){$("error").textContent="Permite ventanas emergentes para abrir CAPTURE. El audio necesita una ventana que permanezca abierta.";return;}
    ui.localActive=true;ui.phaseTo("STARTING");
    ui.startPending=true;ui.pendingSessionId=ui.snapshot?.session_id;
    captureWindow.requestedDirection=ui.directionId;
    $("control-notice").textContent="Mantén CAPTURE abierta. Puedes recargar esta consola sin cortar audio.";
    return;
  }
  const s = newHistory();
  s.direction=ui.directionSupported?ui.directionId:null;
  active = s;
  controls(true);
  ui.phaseTo("STARTING");ui.startedAt=Date.now();
  ui.verifiedProvider=null;ui.lastTranslationFailed=false;
  $("error").textContent = "";
  for (const id of ["partial", "confirmed", "segments", "pending", "ready", "normalized", "normalized-segments", "english", "english-segments", "corrections"]) $(id).textContent = "";
  $("translator").textContent = "Connecting";
  $("translation-status").textContent = "Waiting for configuration";
  $("connection").textContent = "Connecting";
  try {
    // Create/resume in the click gesture, before waiting for WLK.
    s.context = new AudioContext();
    // CAPTURE may receive START before its asynchronous device list is ready.
    // Keep the exact operator selection independently of the popup's <select>.
    const deviceId = captureDeviceId ?? $("microphone").value;
    s.stream = await navigator.mediaDevices.getUserMedia({audio: deviceId ? {deviceId: {exact: deviceId}} : true});
    // A same-origin capture popup receives START via postMessage. Obtain its
    // capture stream before resume so Chromium's WebAudio policy permits it.
    await s.context.resume();
    s.stream.getAudioTracks()[0].onended = () => { if (active === s && !s.stopping) fail(s, new Error("Micrófono desconectado")); };
    const directionQuery=s.direction?`?direction=${encodeURIComponent(s.direction)}`:"";
    const socket = s.socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/session${directionQuery}`, ["operator.v1",ui.token]);
    s.timer = setTimeout(() => fail(s, new Error("Timeout al conectar con WLK")), 120000);
    socket.onmessage = async event => {
      if (active !== s) return;
      try {
        const data = JSON.parse(event.data);
        if(data.protocol_version!==1)throw Error("Backend incompatible");
        if (data.session_id && !s.sessionId) s.sessionId = data.session_id;
        if(data.session_id && data.session_id!==s.sessionId)return;
        debug(`${data.type} ${data.state || data.payload?.type || data.payload?.status || ""}`);
        if(data.type==="operator_command" && data.command==="stop"){await $("stop").onclick();return;}
        if (data.type === "config") {
          if(s.direction && (data.capabilities?.session_direction!==1 || data.direction?.id!==s.direction))
            throw Error("Backend incompatible: direction was not confirmed");
          if(data.capabilities?.operator_console!==1 || data.capabilities?.captions_clear!==1)throw Error("Backend incompatible con M6");
          if (data.capabilities?.terminology_normalizer !== 1) {
            throw new Error("Backend anterior a Milestone 3.1. Reinicia FastAPI y recarga esta página.");
          }
          if (data.capabilities?.translation_engine !== 1) {
            throw new Error("Backend anterior a Milestone 4. Reinicia FastAPI y recarga esta página.");
          }
          if (data.capabilities?.caption_overlay !== 1) {
            throw new Error("Backend anterior a Milestone 5. Reinicia FastAPI para conectar el overlay.");
          }
          if (data.capabilities?.persistent_captions !== 1 || data.capabilities?.caption_latency !== 1) {
            throw new Error("Backend anterior a M5.1. Reinicia FastAPI para captions persistentes y latencias.");
          }
          s.translationStatus = data.translation_status;
          translationStatus(s.translationStatus, 0);ui.translator(s.translationStatus);
          clearTimeout(s.timer);
          $("connection").textContent = "Connected";
          await capture(s);
        } else if (data.type === "asr") {
          if (s.translationStatus) translationStatus(s.translationStatus, data.translation_queue_depth);
          $("partial").textContent = data.transcript.partial_text;
          flow("confirmed", data.transcript.confirmed_text);
          $("segments").textContent = JSON.stringify(data.transcript.segments, null, 2);
          renderSegmentation(s, data.segmentation, data.normalization);
          if (new URLSearchParams(location.search).get("trace_partial") === "1") {
            debug(`PARTIAL raw=${JSON.stringify(data.payload.buffer_transcription)} state=${JSON.stringify(data.transcript.partial_text)} DOM=${JSON.stringify($("partial").textContent)}`);
          }
        } else if (data.type === "segmentation") {
          if (s.translationStatus) translationStatus(s.translationStatus, data.translation_queue_depth);
          renderSegmentation(s, data.segmentation, data.normalization);
        } else if (data.type === "translation") {
          renderTranslation(s, data);
        } else if (data.type === "error") throw new Error(data.message);
        else if (data.state === "stopped") {
          s.finished = true;
          ui.phaseTo("STOPPED");
          $("connection").textContent = "Disconnected — sesión finalizada";
          await release(s);
          if(data.completion==="incomplete")$("error").textContent="STOP incompleto: revisa los diagnósticos de la consola.";
        }
      } catch (error) { await fail(s, error); }
    };
    socket.onerror = () => fail(s, new Error("No se pudo mantener el WebSocket. Revisa ambos servidores y logs."));
    socket.onclose = async () => {
      clearTimeout(s.timer);
      if (active !== s) return;
      if (!s.finished && !s.failed) return fail(s, new Error("Conexión cerrada antes de finalizar; el texto puede estar incompleto."));
      await release(s);
      if (active === s) { active = null; controls(false); }
      $("capture").textContent = "Micrófono inactivo";
    };
  } catch (error) { await fail(s, error); }
};
$("stop").onclick = async () => {
  if(ui.recovery && !ui.captureMode){await ui.command("stop");return;}
  const s = active;
  if (!s || s.stopping) return;
  s.stopping = true;
  ui.phaseTo("STOPPING");
  $("stop").disabled = true;
  $("connection").textContent = "Finalizando…";
  try {
    // Stop forwarding in the worklet, drain both queues, then send binary EOF.
    s.stream.getTracks().forEach(track => track.stop());
    s.worklet.port.postMessage({command: "flush"});
  } catch (error) { await fail(s, error); }
};
window.addEventListener("beforeunload", () => {
  if(ui.captureMode)window.opener?.postMessage({type:"capture_closed"},location.origin);
  active?.stream?.getTracks().forEach(track => track.stop());
  active?.socket?.close();
});
window.addEventListener("message",async event=>{
  if(event.origin!==location.origin)return;
  if(!ui.captureMode && event.source===captureWindow && ["capture_failed","capture_closed"].includes(event.data?.type) && ui.startPending){
    ui.startPending=false;ui.localActive=false;await ui.refresh();
  }
  if(!ui.captureMode && event.source===captureWindow && event.data?.type==="capture_ready"){
    captureWindow.postMessage({type:"capture_start",token:ui.token,deviceId:$("microphone").value,direction:captureWindow.requestedDirection},location.origin);
  }
  if(ui.captureMode && event.source===window.opener && event.data?.type==="capture_start" && !active){
    await ui.ready;ui.token=event.data.token;
    captureDeviceId=typeof event.data.deviceId==="string"?event.data.deviceId:"";
    $("microphone").value=captureDeviceId;
    if(ui.directionSupported){
      if(!["en-es","es-en"].includes(event.data.direction))return;
      ui.directionId=event.data.direction;ui.render();
    }
    $("start").disabled=false;await $("start").onclick();
  }
});
if(ui.captureMode){
  document.body.classList.add("capture-window");
  $("control-notice").textContent="CAPTURE — no cierres esta ventana durante LIVE. La consola principal puede recargarse.";
  ui.ready.then(()=>window.opener?.postMessage({type:"capture_ready"},location.origin));
}
microphones().catch(error => ui.error(error));
