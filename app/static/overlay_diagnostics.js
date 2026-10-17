"use strict";
(function () {
  const element = document.getElementById("overlay-diagnostics");
  let stopped = false;
  async function refresh() {
    try {
      const response = await fetch("/api/overlay/status", {cache: "no-store"});
      if (!response.ok) throw new Error("Caption hub unavailable / backend requires restart");
      const data = await response.json();
      const stages = data.latency_diagnostics?.backend_samples?.at(-1) || {};
      const observers = data.latency_diagnostics?.observers || [];
      const source = [...observers].filter(item => item.sequence).sort((a,b) => b.received_at - a.received_at)[0] || {};
      const ms = value => Number.isFinite(value) ? `${Math.round(value)} ms` : "not measured";
      const translationDepth = data.latency_diagnostics?.translation_queue_depth ?? 0;
      const alerts = [];
      if (translationDepth >= 3) alerts.push("translation queue accumulating");
      if (stages.translation_queue_delay_ms > 1000) alerts.push("translation queue delay > 1 s");
      if (source.visual_queue_depth > 0) alerts.push("visual queue accumulating");
      if (source.renderer_delay_ms > 500) alerts.push("renderer delay > 500 ms");
      element.textContent = [
        `session: ${data.session_id || "none"} / ${data.state}`,
        `overlay connections: ${data.overlay_connections}`,
        `translator state: ${data.translator_state}`,
        `broadcast errors: ${data.broadcast_errors}`,
        `display drops (observer reports): ${data.display_drops}`,
        `drop reasons: ${JSON.stringify(data.display_drop_reasons || {})}`,
        `mock results filtered: ${data.filtered_mock}`,
        `last caption: ${data.last_caption ? `#${data.last_caption.sequence} ${data.last_caption.text}` : "none"}`,
        `ASR first appearance → READY: ${ms(stages.asr_to_ready_ms)}`,
        `latency sample: #${stages.sequence || "none"} / observer sample: #${source.sequence || "none"}`,
        `backend clock resolution: ${ms(data.latency_diagnostics?.backend_clock_resolution_ms)}`,
        `READY → normalized: ${ms(stages.ready_to_normalized_ms)}`,
        `READY → translation started: ${ms(stages.ready_to_translation_started_ms)}`,
        `translation queue delay: ${ms(stages.translation_queue_delay_ms)} / depth: ${translationDepth}`,
        `provider call (last attempt / total): ${ms(stages.provider_last_attempt_ms)} / ${ms(stages.provider_total_ms)}`,
        `translation completed → CaptionHub: ${ms(stages.translation_to_hub_ms)}`,
        `observer: ${source.observer_id || "none"} / visual queue: ${source.visual_queue_depth ?? "n/a"}`,
        `receive → DOM: ${ms(source.renderer_delay_ms)} / double-rAF paint estimate: ${ms(source.paint_delay_ms)}`,
        `Hub delivery estimate: ${ms(source.hub_delivery_estimate_ms)} ± ${ms(source.delivery_uncertainty_ms)}`,
        `READY → visible estimate: ${ms(source.ready_to_visible_estimate_ms)}`,
        `ASR first appearance → visible estimate: ${ms(source.asr_to_visible_estimate_ms)}`,
        `visible captions / lines: ${source.visible_caption_count ?? "n/a"} / ${source.visible_line_count ?? "n/a"}`,
        `rolled-out lines: ${source.rolled_out_lines ?? 0} / coalesced DOM updates: ${source.coalesced_render_updates ?? 0}`,
        `alerts: ${alerts.join("; ") || "none"}`,
      ].join("\n");
    } catch { element.textContent = "Caption hub disconnected / backend requires restart"; }
    if (!stopped) setTimeout(refresh, 2000);
  }
  window.addEventListener("beforeunload", () => { stopped = true; });
  refresh();
})();
