"use strict";
(async () => {
  const element = document.getElementById("caption"), stage = document.getElementById("caption-stage");
  let socket = null, stopped = false, retry = 0, renderer;
  let lastEventId = -1;
  let clock = new OverlayClock(), probeTimer = null, renderSerial = 0, pendingPaint = false, coalesced = 0;
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
      type: "display_drop", session_id: renderer.sessionId, sequence: renderer.seen,
      reason, count: Math.min(20000, count)}));
  };
  renderer = new CaptionPresentation.CaptionRenderer(effective(), {
    now: () => performance.now(),
    measure: (text, size) => { context.font = `600 ${size}px Arial`; return context.measureText(text).width; },
    show: frame => {
      element.textContent = frame.text; element.style.fontSize = `${frame.fontSize}px`;
      element.style.maxWidth = `${renderer.config.max_width}px`;
      element.hidden = false; element.classList.add("visible");
    },
    hide: () => { element.classList.remove("visible"); element.hidden = true; element.textContent = ""; },
    report,
    cleared: sample => {
      renderSerial++; pendingPaint = false;
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({
        type: "render_sample", kind: "clear", session_id: sample.sessionId, sequence: sample.sequence,
        browser_rendered_ms: performance.now(), visual_queue_depth: 0,
        visible_caption_count: 0, visible_line_count: 0, rolled_out_lines: renderer.rolledOutLines || 0}));
    },
    rendered: sample => {
      const serial = ++renderSerial, session = renderer.sessionId;
      if (pendingPaint) coalesced++;
      pendingPaint = true;
      // A double rAF estimates a paint opportunity; it does not observe OBS output.
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (serial !== renderSerial || renderer.generation !== sample.generation ||
            renderer.sessionId !== session || !renderer.current) return;
        pendingPaint = false;
        const painted = performance.now();
        const data = {type: "render_sample", session_id: session, sequence: sample.caption.sequence,
          renderer_delay_ms: sample.renderer_delay_ms,
          paint_delay_ms: Math.max(0, painted - sample.receivedAt),
          browser_received_ms: sample.receivedAt, browser_rendered_ms: painted,
          visual_queue_depth: sample.visual_queue_depth, visible_caption_count: sample.visible_caption_count,
          visible_line_count: sample.visible_line_count, rolled_out_lines: sample.rolled_out_lines,
          coalesced_render_updates: coalesced,
          ...clock.estimate(sample.caption, sample.receivedAt, painted, sample.restore)};
        if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(data));
      }));
    },
  });
  window.addEventListener("resize", () => {
    // Clear outdated measurements instead of clipping content after a resize.
    if (renderer.configure) renderer.configure(effective());
    else {
      if (renderer.current || renderer.queue.length) report("queue_overflow", renderer.queue.length + 1);
      renderer.clear(); renderer.config = effective();
    }
  });
  const connect = () => {
    if (stopped) return;
    renderer.setState("reconnecting");
    socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/overlay`);
    clock = new OverlayClock();
    const probe = () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({type: "clock_probe", client_sent_ms: performance.now()}));
        probeTimer = setTimeout(probe, 10000);
      }
    };
    socket.onopen = probe;
    socket.onmessage = event => {
      const receivedAt = performance.now();
      let data;
      try { data = JSON.parse(event.data); } catch { socket.close(); return; }
      if (data.protocol_version !== 2) { stopped = true; renderer.clear(); socket.close(); return; }
      if (data.type === "clock_sync") { clock.synchronize(data, receivedAt); return; }
      if (data.type === "snapshot") {
        retry = 0; lastEventId = data.event_id;
        if (renderer.sessionId !== data.session_id) renderer.reset(data.session_id);
        if (renderer.restore) {
          renderer.restore(data.captions || (data.caption ? [data.caption] : []), receivedAt);
          renderer.setState(data.state, data.stop_remaining_ms);
        } else {
          renderer.setState(data.state);
          if (data.caption) renderer.enqueue(data.caption,
            Math.max(0, (data.caption.expires_at - data.server_time) * 1000), receivedAt);
        }
        return;
      }
      if (data.event_id <= lastEventId) return;
      lastEventId = data.event_id;
      if (data.type === "session" && data.state === "connecting") {
        renderer.reset(data.session_id); coalesced = 0; pendingPaint = false; renderSerial++;
      }
      if (data.session_id !== renderer.sessionId) return;
      if (data.type === "session") renderer.setState(data.state);
      if (data.type === "caption") renderer.enqueue(data.caption, null, receivedAt);
      if (data.type === "translator") renderer.translatorState = data.state;
    };
    socket.onclose = () => {
      clearTimeout(probeTimer); pendingPaint = false; renderSerial++;
      renderer.setState("disconnected");
      if (!stopped) setTimeout(connect, Math.min(10000, 500 * 2 ** Math.min(retry++, 5)));
    };
    socket.onerror = () => socket.close();
  };
  window.addEventListener("beforeunload", () => { stopped = true; clearTimeout(probeTimer); renderer.clear(); socket?.close(); });
  connect();
})().catch(() => console.error("Overlay initialization failed"));
