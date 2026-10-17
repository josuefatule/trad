"use strict";
(function () {
  const element = document.getElementById("overlay-diagnostics");
  let stopped = false;
  async function refresh() {
    try {
      const response = await fetch("/api/overlay/status", {cache: "no-store"});
      if (!response.ok) throw new Error("Caption hub unavailable / backend requires restart");
      const data = await response.json();
      element.textContent = [
        `session: ${data.session_id || "none"} / ${data.state}`,
        `overlay connections: ${data.overlay_connections}`,
        `translator state: ${data.translator_state}`,
        `broadcast errors: ${data.broadcast_errors}`,
        `display drops (observer reports): ${data.display_drops}`,
        `mock results filtered: ${data.filtered_mock}`,
        `last caption: ${data.last_caption ? `#${data.last_caption.sequence} ${data.last_caption.text}` : "none"}`,
      ].join("\n");
    } catch { element.textContent = "Caption hub disconnected / backend requires restart"; }
    if (!stopped) setTimeout(refresh, 2000);
  }
  window.addEventListener("beforeunload", () => { stopped = true; });
  refresh();
})();
