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

  class TimedCaptionRenderer {
    constructor(config, {measure, show, hide, now = () => Date.now(),
                        schedule = (fn, ms) => setTimeout(fn, ms),
                        cancel = id => clearTimeout(id), report = () => {}, rendered = () => {},
                        cleared = () => {}}) {
      Object.assign(this, {config, measure, show, hide, now, schedule, cancel, report, rendered, cleared});
      this.sessionId = null; this.seen = 0; this.queue = []; this.current = null;
      this.timer = null; this.generation = 0; this.state = "waiting";
      this.tokens = []; this.rolledOutLines = 0;
    }
    reset(sessionId) {
      this.clear(); this.sessionId = sessionId; this.seen = 0;
    }
    clear() {
      this.generation++; this.cancel(this.timer); this.timer = null;
      this.queue = []; this.current = null; this.hide();
      if (this.seen) this.cleared({sessionId: this.sessionId, sequence: this.seen});
    }
    setState(state) {
      this.state = state;
      if (["waiting", "connecting", "error", "disconnected", "reconnecting"].includes(state)) this.clear();
      // stopped drains completed captions; each has a finite reading duration.
    }
    enqueue(caption, snapshotRemainingMs = null, receivedAt = this.now()) {
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
          caption, receivedAt,
          restore: snapshotRemainingMs != null,
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
        this.rendered({caption: frame.caption, receivedAt: frame.receivedAt,
          restore: frame.restore,
          renderer_delay_ms: this.now() - frame.receivedAt, visual_queue_depth: this.queue.length,
          visible_caption_count: 1, visible_line_count: frame.text.split("\n").length,
          rolled_out_lines: 0, generation: this.generation});
        const generation = this.generation;
        const duration = frame.deadline == null ? frame.duration :
          Math.min(frame.duration, frame.deadline - now);
        this.timer = this.schedule(() => {
          if (generation === this.generation) this.advance();
        }, duration);
        return;
      }
      this.hide();
      if (this.seen) this.cleared({sessionId: this.sessionId, sequence: this.seen});
    }
  }

  function rollingLayout(tokens, config, measure) {
    let fontSize = config.font_size;
    for (const token of tokens) {
      const width = measure(token.text, config.font_size);
      if (width > config.max_width) fontSize = Math.min(fontSize,
        Math.floor(config.font_size * config.max_width / width));
    }
    if (fontSize < 8) return {reason: "unreadable_token"};
    const lines = []; let line = [];
    const textOf = words => words.map(word => word.text).join(" ").replace(/\s+([,.;:!?])/g, "$1");
    for (const token of tokens) {
      if (line.length && measure(textOf([...line, token]), fontSize) > config.max_width) {
        lines.push({tokens: line, text: textOf(line)}); line = [];
      }
      line.push(token);
    }
    if (line.length) lines.push({tokens: line, text: textOf(line)});
    return {lines, fontSize};
  }

  class PersistentCaptionRenderer extends TimedCaptionRenderer {
    clear() { super.clear(); this.tokens = []; this.rolledOutLines = 0; }
    setState(state, stopRemainingMs = null) {
      this.state = state;
      this.cancel(this.timer); this.timer = null;
      if (["waiting", "connecting", "error", "disconnected", "reconnecting"].includes(state)) this.clear();
      if (state === "stopped") {
        const generation = this.generation;
        const duration = stopRemainingMs ?? this.config.stop_clear_ms ?? 8000;
        if (duration <= 0) this.clear();
        else this.timer = this.schedule(() => {
          if (generation === this.generation) this.clear();
        }, duration);
      }
    }
    enqueue(caption, unused = null, receivedAt = this.now()) {
      if (!caption || caption.session_id !== this.sessionId || caption.sequence <= this.seen) return;
      this.seen = caption.sequence;
      if (caption.provider === "mock" || caption.text.trimStart().startsWith("[MOCK")) return;
      if (caption.text.length > 20000) { this.report("oversize", 1); return; }
      const added = caption.text.trim().split(/\s+/u).filter(Boolean)
        .map(text => ({text, sequence: caption.sequence}));
      this.roll([...this.tokens, ...added], caption, receivedAt, false);
    }
    roll(tokens, caption, receivedAt, restore) {
      const layout = rollingLayout(tokens, this.config, this.measure);
      if (layout.reason) { this.report(layout.reason, 1); return; }
      const retireCount = Math.max(0, layout.lines.length - this.config.max_lines);
      const retired = layout.lines.slice(0, retireCount).flatMap(line => line.tokens);
      const unseen = restore ? 0 : retired.filter(token => token.sequence === caption.sequence).length;
      if (unseen) this.report("rolling_overflow", unseen);
      this.rolledOutLines = (this.rolledOutLines || 0) + retireCount;
      const visible = layout.lines.slice(-this.config.max_lines);
      this.tokens = visible.flatMap(line => line.tokens);
      this.current = {text: visible.map(line => line.text).join("\n"), fontSize: layout.fontSize,
        caption, receivedAt};
      this.queue = []; // retention never queues or delays a new translation
      if (!this.tokens.length) { this.hide(); return; }
      this.show(this.current);
      this.rendered({caption, receivedAt, restore, renderer_delay_ms: this.now() - receivedAt,
        visual_queue_depth: 0, visible_caption_count: new Set(this.tokens.map(token => token.sequence)).size,
        visible_line_count: visible.length, rolled_out_lines: this.rolledOutLines,
        generation: this.generation});
    }
    restore(captions, receivedAt = this.now()) {
      this.tokens = [];
      const valid = captions.filter(caption => caption.session_id === this.sessionId &&
        caption.provider !== "mock" && !caption.text.trimStart().startsWith("[MOCK"));
      if (!valid.length) return;
      const tokens = valid.flatMap(caption => caption.text.trim().split(/\s+/u).filter(Boolean)
        .map(text => ({text, sequence: caption.sequence})));
      this.seen = Math.max(this.seen, ...valid.map(caption => caption.sequence));
      this.roll(tokens, valid.at(-1), receivedAt, true);
    }
    configure(config) {
      this.config = config;
      if (this.current) this.roll(this.tokens, this.current.caption, this.now(), true);
    }
  }
  class CaptionRenderer {
    constructor(config, dependencies) {
      return config.mode === "timed_queue" ? new TimedCaptionRenderer(config, dependencies) :
        new PersistentCaptionRenderer(config, dependencies);
    }
  }
  const api = {CaptionRenderer, TimedCaptionRenderer, PersistentCaptionRenderer, splitCaption, rollingLayout};
  root.CaptionPresentation = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
