"use strict";
const $ = (id) => document.getElementById(id);
let active = null;
function renderSegmentation(s, result, normalization) {
  if (!result) return;
  $("pending").textContent = result.pending_segment;
  const stamp = value => value == null ? "?" : `${Math.floor(value / 60).toString().padStart(2, "0")}:${(value % 60).toFixed(2).padStart(5, "0")}`;
  const normalizedById = new Map((normalization?.segments || []).map(item => [item.segment_id, item]));
  for (const segment of result.ready_segments) {
    if (s.readyIds.has(segment.id)) continue;
    const item = normalizedById.get(segment.id);
    if (!item) throw new Error("El backend no envió NORMALIZED ES. Reinicia FastAPI y recarga esta página.");
    s.readyIds.add(segment.id);
    $("ready").textContent += `[${stamp(segment.start_time)} → ${stamp(segment.end_time)}] ${segment.reason} · ${segment.word_count} palabras · ${Math.round(segment.latency_ms)} ms\n${segment.text}\n\n`;
    s.normalizedSegments.push(item.normalized_text);
    $("normalized").textContent = compactNormalizedText(s.normalizedSegments);
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
  $("translator").textContent = `${state[0].toUpperCase()}${state.slice(1)}${provider}`;
  $("translation-status").textContent = [
    `provider: ${status?.provider || "none"}`,
    `status: ${state}`,
    `queue depth: ${queueDepth ?? 0}`,
    status?.message ? `detail: ${status.message}` : "",
  ].filter(Boolean).join("\n");
}
function renderTranslation(s, data) {
  if (data.session_id !== s.sessionId) {
    debug(`translation discarded for stale session ${data.session_id}`);
    return;
  }
  const result = data.translation;
  s.translationResults.set(result.sequence, result);
  while (s.translationResults.has(s.nextTranslationSequence)) {
    const ready = s.translationResults.get(s.nextTranslationSequence);
    s.translationResults.delete(s.nextTranslationSequence++);
    if (ready.success) {
      s.translatedSegments.push(ready.translated_text);
      $("english").textContent = compactNormalizedText(s.translatedSegments);
    }
    $("translation-status").textContent = [
      `provider: ${ready.provider}`,
      `status: ${ready.success ? "completed" : "error"}`,
      `segment: ${ready.segment_id} (#${ready.sequence})`,
      `translation latency: ${Math.round(ready.latency_ms)} ms`,
      `queue delay: ${Math.round(ready.queue_delay_ms)} ms`,
      `queue depth: ${data.translation_queue_depth}`,
      `attempts: ${ready.attempt_count}`,
      ready.error ? `error: ${ready.error}` : "",
    ].filter(Boolean).join("\n");
  }
}
function debug(message) {
  $("debug").textContent = `${new Date().toISOString()} ${message}\n` +
    $("debug").textContent.split("\n").slice(0, 99).join("\n");
}
function controls(busy) {
  $("start").disabled = busy;
  $("refresh").disabled = busy;
  $("microphone").disabled = busy;
  $("stop").disabled = true;
}
async function microphones(permission = false) {
  if (permission) {
    const temporary = await navigator.mediaDevices.getUserMedia({audio: true});
    temporary.getTracks().forEach(track => track.stop());
  }
  const selected = $("microphone").value;
  const devices = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === "audioinput");
  $("microphone").replaceChildren(new Option("Predeterminado", ""),
    ...devices.map((d, i) => new Option(d.label || `Micrófono ${i + 1}`, d.deviceId)));
  if (devices.some(d => d.deviceId === selected)) $("microphone").value = selected;
}
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
  $("error").textContent = error.message || String(error);
  $("connection").textContent = "Error / Disconnected";
  debug($("error").textContent);
  s.socket?.close();
  await release(s);
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
  $("stop").disabled = false;
  debug("audio stream started");
}
$("refresh").onclick = () => microphones(true).catch(error => { $("error").textContent = error.message; });
$("start").onclick = async () => {
  const s = {readyIds: new Set(), normalizedSegments: [], translatedSegments: [],
    translationResults: new Map(), nextTranslationSequence: 1, sessionId: null};
  active = s;
  controls(true);
  $("error").textContent = "";
  for (const id of ["partial", "confirmed", "segments", "pending", "ready", "normalized", "normalized-segments", "english", "corrections"]) $(id).textContent = "";
  $("translator").textContent = "Connecting";
  $("translation-status").textContent = "Waiting for configuration";
  $("connection").textContent = "Connecting";
  try {
    // Create/resume in the click gesture, before waiting for WLK.
    s.context = new AudioContext();
    await s.context.resume();
    const deviceId = $("microphone").value;
    s.stream = await navigator.mediaDevices.getUserMedia({audio: deviceId ? {deviceId: {exact: deviceId}} : true});
    s.stream.getAudioTracks()[0].onended = () => { if (active === s && !s.stopping) fail(s, new Error("Micrófono desconectado")); };
    const socket = s.socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/session`);
    s.timer = setTimeout(() => fail(s, new Error("Timeout al conectar con WLK")), 30000);
    socket.onmessage = async event => {
      if (active !== s) return;
      try {
        const data = JSON.parse(event.data);
        if (data.session_id && !s.sessionId) s.sessionId = data.session_id;
        debug(`${data.type} ${data.state || data.payload?.type || data.payload?.status || ""}`);
        if (data.type === "config") {
          if (data.capabilities?.terminology_normalizer !== 1) {
            throw new Error("Backend anterior a Milestone 3.1. Reinicia FastAPI y recarga esta página.");
          }
          if (data.capabilities?.translation_engine !== 1) {
            throw new Error("Backend anterior a Milestone 4. Reinicia FastAPI y recarga esta página.");
          }
          s.translationStatus = data.translation_status;
          translationStatus(s.translationStatus, 0);
          clearTimeout(s.timer);
          $("connection").textContent = "Connected";
          await capture(s);
        } else if (data.type === "asr") {
          if (s.translationStatus) translationStatus(s.translationStatus, data.translation_queue_depth);
          $("partial").textContent = data.transcript.partial_text;
          $("confirmed").textContent = data.transcript.confirmed_text;
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
          $("connection").textContent = "Disconnected — sesión finalizada";
          await release(s);
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
  const s = active;
  if (!s || s.stopping) return;
  s.stopping = true;
  $("stop").disabled = true;
  $("connection").textContent = "Finalizando…";
  try {
    // Stop forwarding in the worklet, drain both queues, then send binary EOF.
    s.stream.getTracks().forEach(track => track.stop());
    s.worklet.port.postMessage({command: "flush"});
  } catch (error) { await fail(s, error); }
};
window.addEventListener("beforeunload", () => {
  active?.stream?.getTracks().forEach(track => track.stop());
  active?.socket?.close();
});
microphones().catch(error => { $("error").textContent = error.message; });
