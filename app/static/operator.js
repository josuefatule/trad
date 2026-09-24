"use strict";
const $ = (id) => document.getElementById(id);
let active = null;
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
  const s = {};
  active = s;
  controls(true);
  $("error").textContent = "";
  for (const id of ["partial", "confirmed", "segments"]) $(id).textContent = "";
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
        debug(`${data.type} ${data.state || data.payload?.type || data.payload?.status || ""}`);
        if (data.type === "config") {
          clearTimeout(s.timer);
          $("connection").textContent = "Connected";
          await capture(s);
        } else if (data.type === "asr") {
          $("partial").textContent = data.transcript.partial_text;
          $("confirmed").textContent = data.transcript.confirmed_text;
          $("segments").textContent = JSON.stringify(data.transcript.segments, null, 2);
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
