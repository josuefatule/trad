"use strict";
(async () => {
  const response = await fetch(`/api/overlay/config${location.search}`);
  if (!response.ok) {
    document.getElementById("geometry-status").textContent = "Invalid overlay configuration; no captions rendered.";
    return;
  }
  const config = await response.json();
  const element = document.getElementById("caption"), status = document.getElementById("preview-status");
  const stage = document.getElementById("caption-stage");
  const viewport = document.getElementById("preview-viewport"), surface = document.getElementById("overlay-canvas");
  const effective = () => {
    const geometry = OverlayGeometry.geometry(config, config.canvas_width, config.canvas_height);
    document.getElementById("geometry-status").textContent =
      `${config.canvas_width} × ${config.canvas_height}; captions (${config.region_x}, ${config.region_y}), ${config.region_width} × ${config.region_height}; ${geometry.maxLines}/${config.max_lines} lines. ${geometry.warning}`;
    const availableHeight = Math.max(1, innerHeight - document.querySelector("header").offsetHeight - 24);
    viewport.style.width = `${Math.max(1, Math.min(innerWidth - 40, config.canvas_width,
      availableHeight * config.canvas_width / config.canvas_height))}px`;
    viewport.style.aspectRatio = `${config.canvas_width} / ${config.canvas_height}`;
    const width = viewport.clientWidth, height = width * config.canvas_height / config.canvas_width;
    const result = OverlayGeometry.apply(config, width, height, surface, stage, element);
    const band = document.getElementById("preview-band");
    Object.assign(band.style, {left: `${config.region_x}px`, top: `${config.region_y}px`,
      width: `${config.region_width}px`, height: `${config.region_height}px`});
    return result.config;
  };
  const ctx = document.createElement("canvas").getContext("2d");
  let session = 0;
  let arrivals = [];
  const renderer = new CaptionPresentation.CaptionRenderer(effective(), {
    now: () => performance.now(),
    measure: (text, size) => { ctx.font = `600 ${size}px Arial`; return ctx.measureText(text).width; },
    show: frame => {
      element.textContent = frame.text; element.style.fontSize = `${frame.fontSize}px`;
      element.hidden = false; element.classList.add("visible");
    },
    hide: () => { element.hidden = true; element.textContent = ""; },
    report: (reason, count) => {
      status.textContent = `Display policy: ${reason}, ${count} frames discarded`;
      effective();
    },
  });
  window.addEventListener("resize", () => {
    const settings = effective();
    if (renderer.configure) renderer.configure(settings);
    // Scaling the complete canvas does not change logical text measurements.
    else renderer.config = settings;
  });
  const reset = () => {
    arrivals.forEach(clearTimeout); arrivals = [];
    renderer.reset(`demo-${++session}`); renderer.setState("live");
    status.textContent = `New local demo session / ${config.mode}`;
    effective();
  };
  document.getElementById("reset").onclick = reset;
  document.getElementById("play").onclick = () => {
    reset();
    const samples = ["Welcome to this local caption preview.",
      "Unicode: café, naïve, renin–angiotensin–aldosterone. <b>This is text, never HTML.</b>",
      "This deliberately long caption is presented in consecutive reading blocks instead of hiding the extra lines. The same presentation renderer runs in the production overlay and keeps whole words together while respecting the configured maximum number of visible lines."];
    const sessionId = renderer.sessionId;
    samples.forEach((text, index) => arrivals.push(setTimeout(() => renderer.enqueue({session_id: sessionId,
      sequence: index + 1, provider: "demo-fixture", text}), index * 2500)));
  };
  document.getElementById("stop").onclick = () => {
    arrivals.forEach(clearTimeout); arrivals = [];
    renderer.setState("stopped"); status.textContent = `STOP: clear after ${config.stop_clear_ms} ms`;
    effective();
  };
  reset();
})();
