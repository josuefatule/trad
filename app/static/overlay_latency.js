/* Explicit clock synchronization; no subtraction of unrelated clocks. */
(function (root) {
  "use strict";
  class OverlayClock {
    constructor() { this.sample = null; }
    synchronize(data, received) {
      const start = data.client_sent_ms, serverStart = data.server_received_mono_ms;
      const serverEnd = data.server_sent_mono_ms;
      if (![start, serverStart, serverEnd, received].every(Number.isFinite) ||
          received < start || serverEnd < serverStart) return;
      const networkRtt = Math.max(0, received - start - (serverEnd - serverStart));
      const resolution = Number.isFinite(data.server_clock_resolution_ms) ?
        Math.max(0, data.server_clock_resolution_ms) : 0;
      const sample = {offset: ((serverStart - start) + (serverEnd - received)) / 2,
        uncertainty: networkRtt / 2 + resolution, at: received};
      if (!this.sample || received - this.sample.at > 20000 ||
          sample.uncertainty < this.sample.uncertainty) this.sample = sample;
    }
    estimate(caption, received, painted, restore = false) {
      if (restore || !this.sample || received - this.sample.at > 30000 ||
          !Number.isFinite(caption.published_mono_ms)) return {};
      const delivery = Math.max(0, received + this.sample.offset - caption.published_mono_ms);
      const localPaint = Math.max(0, painted - received);
      const result = {hub_delivery_estimate_ms: delivery,
        delivery_uncertainty_ms: this.sample.uncertainty};
      if (Number.isFinite(caption.latency?.ready_to_hub_ms))
        result.ready_to_visible_estimate_ms = caption.latency.ready_to_hub_ms + delivery + localPaint;
      if (Number.isFinite(caption.latency?.asr_to_hub_ms))
        result.asr_to_visible_estimate_ms = caption.latency.asr_to_hub_ms + delivery + localPaint;
      return result;
    }
  }
  root.OverlayClock = OverlayClock;
  if (typeof module !== "undefined") module.exports = {OverlayClock};
})(typeof window !== "undefined" ? window : globalThis);
