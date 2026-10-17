"use strict";
(async () => {
  const element = document.getElementById("caption"), stage = document.getElementById("caption-stage");
  let socket = null, stopped = false, retry = 0, renderer;
  let lastEventId = -1;
  const response = await fetch(`/api/overlay/config${location.search}`);
  if (!response.ok) { console.error("Invalid overlay configuration"); return; }
  const config = await response.json();
  stage.style.alignItems = {bottom: "flex-end", top: "flex-start", center: "center"}[config.position];
  element.style.backgroundColor = `rgba(0, 0, 0, ${config.background_opacity})`;
  const canvas = document.createElement("canvas"), context = canvas.getContext("2d");
  const effective = () => {
    const offset = Math.min(config.bottom_offset, Math.max(0,
      innerHeight - config.font_size * 1.2 * config.max_lines - 72));
    stage.style.paddingBottom = config.position === "bottom" ? `${offset}px` : "24px";
    stage.style.paddingTop = config.position === "top" ? `${offset}px` : "24px";
    return {...config, max_width: Math.max(40, Math.min(config.max_width, innerWidth - 92))};
  };
  const report = (reason, count) => {
    console.warn("overlay_display_drop", {reason, count});
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({
      type: "display_drop", session_id: renderer.sessionId, reason, count: Math.min(256, count)}));
  };
  renderer = new CaptionPresentation.CaptionRenderer(effective(), {
    measure: (text, size) => { context.font = `600 ${size}px Arial`; return context.measureText(text).width; },
    show: frame => {
      element.textContent = frame.text; element.style.fontSize = `${frame.fontSize}px`;
      element.style.maxWidth = `${renderer.config.max_width}px`;
      element.hidden = false; element.classList.add("visible");
    },
    hide: () => { element.classList.remove("visible"); element.hidden = true; element.textContent = ""; },
    report,
  });
  window.addEventListener("resize", () => {
    // Clear outdated measurements instead of clipping content after a resize.
    if (renderer.current || renderer.queue.length) report("queue_overflow", renderer.queue.length + 1);
    renderer.clear(); renderer.config = effective();
  });
  const connect = () => {
    if (stopped) return;
    renderer.setState("reconnecting");
    socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/overlay`);
    socket.onmessage = event => {
      let data;
      try { data = JSON.parse(event.data); } catch { socket.close(); return; }
      if (data.protocol_version !== 1) { stopped = true; renderer.clear(); socket.close(); return; }
      if (data.type === "snapshot") {
        retry = 0; lastEventId = data.event_id;
        if (renderer.sessionId !== data.session_id) renderer.reset(data.session_id);
        renderer.setState(data.state);
        if (data.caption) renderer.enqueue(data.caption,
          Math.max(0, (data.caption.expires_at - data.server_time) * 1000));
        return;
      }
      if (data.event_id <= lastEventId) return;
      lastEventId = data.event_id;
      if (data.type === "session" && data.state === "connecting") renderer.reset(data.session_id);
      if (data.session_id !== renderer.sessionId) return;
      if (data.type === "session") renderer.setState(data.state);
      if (data.type === "caption") renderer.enqueue(data.caption);
      if (data.type === "translator") renderer.translatorState = data.state;
    };
    socket.onclose = () => {
      renderer.setState("disconnected");
      if (!stopped) setTimeout(connect, Math.min(10000, 500 * 2 ** Math.min(retry++, 5)));
    };
    socket.onerror = () => socket.close();
  };
  window.addEventListener("beforeunload", () => { stopped = true; renderer.clear(); socket?.close(); });
  connect();
})().catch(() => console.error("Overlay initialization failed"));
