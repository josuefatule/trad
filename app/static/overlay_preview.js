"use strict";
(async () => {
  const config = await (await fetch(`/api/overlay/config${location.search}`)).json();
  config.max_width = Math.min(config.max_width, innerWidth - 92);
  const element = document.getElementById("caption"), status = document.getElementById("preview-status");
  const stage = document.getElementById("caption-stage");
  stage.style.alignItems = {bottom: "flex-end", top: "flex-start", center: "center"}[config.position];
  if (config.position === "bottom") stage.style.paddingBottom = `${config.bottom_offset}px`;
  if (config.position === "top") stage.style.paddingTop = `${config.bottom_offset}px`;
  element.style.backgroundColor = `rgba(0,0,0,${config.background_opacity})`;
  const ctx = document.createElement("canvas").getContext("2d");
  let session = 0;
  let arrivals = [];
  const renderer = new CaptionPresentation.CaptionRenderer(config, {
    now: () => performance.now(),
    measure: (text, size) => { ctx.font = `600 ${size}px Arial`; return ctx.measureText(text).width; },
    show: frame => {
      element.textContent = frame.text; element.style.fontSize = `${frame.fontSize}px`;
      element.hidden = false; element.classList.add("visible");
    },
    hide: () => { element.hidden = true; element.textContent = ""; },
    report: (reason, count) => { status.textContent = `Display policy: ${reason}, ${count} frames discarded`; },
  });
  const reset = () => {
    arrivals.forEach(clearTimeout); arrivals = [];
    renderer.reset(`demo-${++session}`); renderer.setState("live");
    status.textContent = `New local demo session / ${config.mode}`;
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
  };
  reset();
})();
