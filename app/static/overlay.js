"use strict";
(async () => {
  const element = document.getElementById("caption"), stage = document.getElementById("caption-stage");
  const surface = document.getElementById("overlay-canvas");
  const applyStyle = style => {
    if (/^#[0-9a-f]{6}$/i.test(style?.text_color)) element.style.color = style.text_color;
    if (/^#[0-9a-f]{6}$/i.test(style?.background_color)) {
      for (const node of [document.documentElement, document.body])
        node.style.setProperty("background", style.background_color, "important");
    }
  };
  let socket = null, stopped = false, retry = 0, renderer;
  let retryTimer=null;
  let disconnectedSince=null;
  let lastEventId = -1;
  let visualGeneration = -1, clearedThrough = 0;
  let clock = new OverlayClock(), probeTimer = null, renderSerial = 0, pendingPaint = false, coalesced = 0;
  const response = await fetch(`/api/overlay/config${location.search}`);
  if (!response.ok) { console.error("Invalid overlay configuration"); return; }
  const config = await response.json();
  const canvas = document.createElement("canvas"), context = canvas.getContext("2d");
  const effective = () => {
    const result = OverlayGeometry.apply(config, innerWidth, innerHeight, surface, stage, element);
    if (result.geometry.warning) console.warn("overlay_geometry", result.geometry.warning);
    return result.config;
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
        visual_generation: visualGeneration,
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
          visual_generation: visualGeneration,
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
    const connection = socket;
    clock = new OverlayClock();
    const probe = () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({type: "clock_probe", client_sent_ms: performance.now()}));
        probeTimer = setTimeout(probe, 10000);
      }
    };
    socket.onopen = probe;
    socket.onmessage = event => {
      if(socket !== connection)return;
      const receivedAt = performance.now();
      let data;
      try { data = JSON.parse(event.data); } catch { socket.close(); return; }
      if (data.protocol_version !== 3) { stopped = true; renderer.clear(); socket.close(); return; }
      if(data.direction?.target_language && (data.type==="snapshot" || (data.type==="session" && data.state==="connecting")))
        document.documentElement.lang=data.direction.target_language;
      if (data.type === "clock_sync") { clock.synchronize(data, receivedAt); return; }
      if (data.type === "snapshot") {
        if(data.session_id===renderer.sessionId && ((data.visual_generation ?? 0)<visualGeneration || data.event_id<lastEventId))return;
        socket.send(JSON.stringify({type:"connection_health",session_id:data.session_id,attempts:retry,
          downtime_ms:disconnectedSince===null?0:Math.max(0,performance.now()-disconnectedSince)}));
        retry = 0;disconnectedSince=null; lastEventId = data.event_id;
        applyStyle(data.overlay_style);
        if (renderer.sessionId !== data.session_id) renderer.reset(data.session_id);
        visualGeneration = data.visual_generation ?? 0;
        clearedThrough = data.cleared_through_sequence ?? 0;
        renderer.clear(); renderer.seen = Math.max(renderer.seen, clearedThrough);
        if (renderer.restore) {
          renderer.restore((data.captions || (data.caption ? [data.caption] : [])).filter(item=>item.sequence>clearedThrough), receivedAt);
          renderer.setState(data.state, data.stop_remaining_ms);
        } else {
          renderer.setState(data.state);
          if (data.caption && data.caption.sequence>clearedThrough) renderer.enqueue(data.caption,
            Math.max(0, (data.caption.expires_at - data.server_time) * 1000), receivedAt);
        }
        return;
      }
      if (data.event_id <= lastEventId) return;
      lastEventId = data.event_id;
      if (data.type === "overlay_style") {
        applyStyle(data.overlay_style);
        return;
      }
      if (data.type === "session" && data.state === "connecting") {
        renderer.reset(data.session_id); coalesced = 0; pendingPaint = false; renderSerial++;
        visualGeneration = data.visual_generation ?? 0; clearedThrough = 0;
      }
      if (data.session_id !== renderer.sessionId) return;
      const generation = data.visual_generation ?? 0;
      if (generation < visualGeneration) return;
      if (data.type === "captions_cleared" || generation > visualGeneration) {
        visualGeneration = generation;
        clearedThrough = Math.max(clearedThrough, data.cleared_through_sequence ?? 0);
        renderer.clear(); renderer.seen = Math.max(renderer.seen, clearedThrough);
        if(data.type === "captions_cleared")return;
      }
      if (data.type === "session") renderer.setState(data.state);
      if (data.type === "caption" && data.caption.sequence > clearedThrough) renderer.enqueue(data.caption, null, receivedAt);
      if (data.type === "translator") renderer.translatorState = data.state;
    };
    socket.onclose = () => {
      if(socket !== connection)return;
      clearTimeout(probeTimer); pendingPaint = false; renderSerial++;
      renderer.setState("disconnected");
      if(disconnectedSince===null)disconnectedSince=performance.now();
      if (!stopped && retry<(config.reconnect_attempts ?? 8)) {
        const delay=Math.min(config.reconnect_max_ms ?? 10000,(config.reconnect_base_ms ?? 500)*2**Math.min(retry++,10))*(.75+.25*Math.random());
        console.warn("overlay_reconnect",{attempt:retry,delay_ms:delay});
        retryTimer=setTimeout(connect,delay);
      } else if(!stopped) console.error("overlay_retries_exhausted: reload Browser Source after restoring FastAPI");
    };
    socket.onerror = () => socket.close();
  };
  window.addEventListener("beforeunload", () => { stopped = true; clearTimeout(probeTimer);clearTimeout(retryTimer); renderer.clear(); socket?.close(); });
  connect();
})().catch(() => console.error("Overlay initialization failed"));
