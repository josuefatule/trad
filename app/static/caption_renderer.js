/* Presentation only: no microphone, network, ASR, or translator dependencies. */
(function (root) {
  "use strict";
  function splitCaption(text, config, measure) {
    const words = text.trim().split(/\s+/u).filter(Boolean);
    const frames = [];
    let lines = [], line = "", fontSize = config.font_size;
    const flush = () => {
      if (line) lines.push(line);
      if (lines.length) frames.push({text: lines.join("\n"), fontSize});
      lines = []; line = ""; fontSize = config.font_size;
    };
    for (const word of words) {
      if (measure(word, fontSize) > config.max_width) {
        flush();
        const tokenFontSize = Math.min(config.font_size,
          Math.floor(config.font_size * config.max_width / measure(word, config.font_size)));
        if (tokenFontSize < 8) return {frames: [], reason: "unreadable_token"};
        frames.push({text: word, fontSize: tokenFontSize});
        continue;
      }
      const candidate = line ? `${line} ${word}` : word;
      if (line && measure(candidate, fontSize) > config.max_width) {
        lines.push(line); line = "";
        if (lines.length === config.max_lines) flush();
      }
      line = line ? `${line} ${word}` : word;
    }
    flush();
    return {frames};
  }

  class CaptionRenderer {
    constructor(config, {measure, show, hide, now = () => Date.now(),
                        schedule = (fn, ms) => setTimeout(fn, ms),
                        cancel = id => clearTimeout(id), report = () => {}}) {
      Object.assign(this, {config, measure, show, hide, now, schedule, cancel, report});
      this.sessionId = null; this.seen = 0; this.queue = []; this.current = null;
      this.timer = null; this.generation = 0; this.state = "waiting";
    }
    reset(sessionId) {
      this.clear(); this.sessionId = sessionId; this.seen = 0;
    }
    clear() {
      this.generation++; this.cancel(this.timer); this.timer = null;
      this.queue = []; this.current = null; this.hide();
    }
    setState(state) {
      this.state = state;
      if (["waiting", "connecting", "error", "disconnected", "reconnecting"].includes(state)) this.clear();
      // stopped drains completed captions; each has a finite reading duration.
    }
    enqueue(caption, snapshotRemainingMs = null) {
      if (!caption || caption.session_id !== this.sessionId || caption.sequence <= this.seen) return;
      this.seen = caption.sequence;
      if (caption.provider === "mock" || caption.text.trimStart().startsWith("[MOCK")) return;
      if (caption.text.length > 20000) { this.report("oversize", 1); return; }
      const split = splitCaption(caption.text, this.config, this.measure);
      if (split.reason) { this.report(split.reason, 1); return; }
      const now = this.now();
      for (const frame of split.frames) {
        const reading = frame.text.split(/\s+/u).length / this.config.reading_wps * 1000;
        const duration = Math.max(this.config.min_display_ms, Math.min(this.config.max_display_ms, reading));
        this.queue.push({...frame, duration, queuedAt: now,
          deadline: snapshotRemainingMs == null ? null : now + snapshotRemainingMs});
      }
      let dropped = 0;
      // Bound both frame count and estimated display backlog, keeping the newest.
      const duration = () => this.queue.reduce((sum, frame) => sum + frame.duration, 0);
      while (this.queue.length > this.config.visual_queue_max ||
             (this.queue.length > 1 && duration() > this.config.max_backlog_ms)) {
        this.queue.shift(); dropped++;
      }
      if (dropped) this.report("queue_overflow", dropped);
      if (!this.current) this.advance();
    }
    advance() {
      this.current = null;
      while (this.queue.length) {
        const frame = this.queue.shift(), now = this.now();
        if (now - frame.queuedAt > this.config.max_backlog_ms ||
            (frame.deadline != null && now >= frame.deadline)) {
          this.report("queue_overflow", 1); continue;
        }
        this.current = frame;
        this.show(frame);
        const generation = this.generation;
        const duration = frame.deadline == null ? frame.duration :
          Math.min(frame.duration, frame.deadline - now);
        this.timer = this.schedule(() => {
          if (generation === this.generation) this.advance();
        }, duration);
        return;
      }
      this.hide();
    }
  }
  const api = {CaptionRenderer, splitCaption};
  root.CaptionPresentation = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
