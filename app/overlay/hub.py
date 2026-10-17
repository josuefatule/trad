"""One active publisher, many bounded read-only subscribers, one event loop."""
import asyncio
from dataclasses import dataclass, field
from dataclasses import asdict
from collections import deque, Counter
import json
import math
import logging
import time
from app.translation.timing import stage_durations

logger = logging.getLogger("captions")


@dataclass(eq=False)
class Subscriber:
    queue: asyncio.Queue
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    observer_id: int = 0
    diagnostics: dict = field(default_factory=dict)


class CaptionHub:
    protocol_version = 2

    def __init__(self, config, *, subscriber_limit=32, queue_size=64, clock=time.time,
                 monotonic_clock=time.monotonic):
        self.config = config
        self.subscriber_limit = subscriber_limit
        self.queue_size = queue_size
        self.clock = clock
        self.monotonic_clock = monotonic_clock
        self.session_id = None
        self.state = "waiting"
        self.sequence = 0
        self.last_caption = None
        self.event_id = 0
        self.subscribers = set()
        self.broadcast_errors = 0
        self.stale_events = 0
        self.filtered_mock = 0
        self.display_drops = 0
        self.display_drop_reasons = Counter()
        self.affected_sequences = deque(maxlen=128)
        self.translator_state = "unknown"
        self._telemetry_budget = 20
        self._observer_serial = 0
        self.caption_history = deque(maxlen=128)
        self.stopped_at = None
        self.translation_queue_depth = 0
        self.translation_status_getter = None
        self.translation_queue_max = 0
        self.latency_samples = deque(maxlen=128)
        self.client_samples = deque(maxlen=128)

    def _event(self, kind, **values):
        self.event_id += 1
        message = {"type": kind, "protocol_version": self.protocol_version,
                   "event_id": self.event_id, "session_id": self.session_id, **values}
        for subscriber in tuple(self.subscribers):
            try:
                subscriber.queue.put_nowait(message)
            except asyncio.QueueFull:
                # Evict and close, rather than block the producer or drop silently.
                self.broadcast_errors += 1
                subscriber.closed.set()
                self.subscribers.discard(subscriber)
                logger.warning("session=%s overlay_slow_subscriber_disconnected", self.session_id)

    def snapshot(self):
        caption = self.last_caption
        stop_remaining = (max(0., self.config.stop_clear_ms - (self.clock() - self.stopped_at) * 1000)
                          if self.stopped_at is not None else None)
        persistent = self.config.mode == "persistent_rolling"
        if caption and ((not persistent and caption["expires_at"] <= self.clock())
                        or (persistent and stop_remaining == 0)
                        or self.state in {"waiting", "connecting", "disconnected", "error"}):
            caption = None
        return {"type": "snapshot", "protocol_version": self.protocol_version,
                "event_id": self.event_id, "session_id": self.session_id,
                "state": self.state, "sequence": self.sequence,
                "translator_state": self.translator_state,
                "caption": caption, "server_time": self.clock(),
                "captions": list(self.caption_history) if caption and persistent else [],
                "stop_remaining_ms": stop_remaining, "mode": self.config.mode}

    def subscribe(self):
        if len(self.subscribers) >= self.subscriber_limit:
            raise ValueError("Overlay subscriber limit reached")
        subscriber = Subscriber(asyncio.Queue(maxsize=self.queue_size))
        self._observer_serial += 1
        subscriber.observer_id = self._observer_serial
        # Synchronous atomic registration + snapshot: no await/race between them.
        self.subscribers.add(subscriber)
        subscriber.queue.put_nowait({**self.snapshot(), "observer_id": subscriber.observer_id})
        return subscriber

    def unsubscribe(self, subscriber):
        self.subscribers.discard(subscriber)
        subscriber.closed.set()

    def begin(self, session_id):
        if self.state in {"connecting", "live", "draining"}:
            raise ValueError("An audio session is already active; stop it before START")
        self.session_id = session_id
        self.sequence = 0
        self.last_caption = None
        self.caption_history.clear()
        self.stopped_at = None
        self.latency_samples.clear()
        self.client_samples.clear()
        self.display_drops = 0
        self.display_drop_reasons.clear()
        self.affected_sequences.clear()
        self.translation_queue_depth = self.translation_queue_max = 0
        self.translation_status_getter = None
        for subscriber in self.subscribers:
            subscriber.diagnostics = {}
        self.translator_state = "unknown"
        self.state = "connecting"
        self._event("session", state=self.state)

    def set_state(self, session_id, state):
        if session_id != self.session_id:
            self.stale_events += 1
            return
        self.state = state
        if state == "stopped":
            self.stopped_at = self.clock()
        if state in {"disconnected", "error"}:
            self.last_caption = None
            self.caption_history.clear()
            for subscriber in self.subscribers:
                subscriber.diagnostics = {}
        self._event("session", state=state)

    def publish(self, result):
        if result.session_id != self.session_id or self.state not in {"live", "draining"}:
            self.stale_events += 1
            return False
        if result.sequence <= self.sequence:
            return False
        if result.sequence != self.sequence + 1:
            self.broadcast_errors += 1
            logger.error("session=%s overlay_sequence_gap expected=%d received=%d",
                         self.session_id, self.sequence + 1, result.sequence)
            return False
        self.sequence = result.sequence
        if not result.success:
            self.translator_state = "error"
            self._event("translator", state="error", sequence=result.sequence)
            return False
        text = result.translated_text or ""
        if result.provider == "mock" or text.lstrip().startswith("[MOCK"):
            self.filtered_mock += 1
            self.translator_state = "mock_filtered"
            self._event("translator", state="mock_filtered", sequence=result.sequence)
            return False
        if not text.strip() or len(text) > 20000:
            self.display_drops += 1
            self.display_drop_reasons["hub_invalid_caption"] += 1
            self.affected_sequences.append(result.sequence)
            self._event("translator", state="invalid_caption", sequence=result.sequence)
            logger.warning("session=%s overlay_caption_rejected sequence=%d", self.session_id, result.sequence)
            return False
        self.translator_state = "ready"
        now = self.clock()
        published_mono = self.monotonic_clock()
        durations = stage_durations(result.timing, published_mono)
        self.last_caption = {"session_id": result.session_id, "sequence": result.sequence,
                             "segment_id": result.segment_id, "text": text,
                             "provider": result.provider, "published_at": now,
                             "expires_at": now + self.config.max_display_ms / 1000,
                             "published_mono_ms": published_mono * 1000,
                             "timing": asdict(result.timing) if result.timing else None,
                             "latency": durations,
                             "translation_queue_depth": self.translation_queue_depth}
        self.caption_history.append(self.last_caption)
        while sum(len(item["text"]) for item in self.caption_history) > 20000:
            self.caption_history.popleft()
        self.latency_samples.append({"sequence": result.sequence, **durations})
        logger.info("session=%s caption_latency sequence=%d %s", self.session_id, result.sequence,
                    json.dumps(durations))
        self._event("caption", caption=self.last_caption)
        return True

    def diagnostics(self):
        return {"session_id": self.session_id, "state": self.state,
                "overlay_connections": len(self.subscribers),
                "last_caption": self.last_caption,
                "broadcast_errors": self.broadcast_errors,
                "stale_events": self.stale_events, "filtered_mock": self.filtered_mock,
                "display_drops": self.display_drops, "translator_state": self.translator_state,
                "display_drop_reasons": dict(self.display_drop_reasons),
                "affected_sequences": sorted(set(self.affected_sequences)),
                "latency_diagnostics": self.latency_diagnostics()}

    def record_translation_status(self, session_id, snapshot):
        if session_id == self.session_id:
            self.translation_queue_depth = snapshot["queue_depth"]
            self.translation_queue_max = max(self.translation_queue_max, snapshot["queue_depth"])

    def record_client_sample(self, subscriber, data):
        if data.get("session_id") != self.session_id or subscriber not in self.subscribers:
            return
        allowed = {"sequence", "renderer_delay_ms", "paint_delay_ms", "hub_delivery_estimate_ms",
                   "delivery_uncertainty_ms", "ready_to_visible_estimate_ms", "asr_to_visible_estimate_ms",
                   "visual_queue_depth", "visible_caption_count", "visible_line_count", "rolled_out_lines",
                   "browser_received_ms", "browser_rendered_ms"}
        allowed.add("coalesced_render_updates")
        sample = {key: value for key, value in data.items() if key in allowed}
        if (type(sample.get("sequence")) is not int or not 1 <= sample["sequence"] <= self.sequence
                or sample["sequence"] < subscriber.diagnostics.get("sequence", 0)):
            return
        if any(type(value) not in (int, float) or not math.isfinite(value)
               or not 0 <= value <= 1e12 for value in sample.values()):
            return
        sample.update(observer_id=subscriber.observer_id, received_at=self.clock(),
                      render_measurement="DOM_clear" if data.get("kind") == "clear" else
                      "double_requestAnimationFrame_estimate")
        subscriber.diagnostics = sample
        self.client_samples.append(sample)

    def latency_diagnostics(self):
        if self.translation_status_getter is not None:
            self.record_translation_status(self.session_id, self.translation_status_getter())
        return {"translation_queue_depth": self.translation_queue_depth,
                "backend_clock_resolution_ms": time.get_clock_info("monotonic").resolution * 1000,
                "translation_queue_max": self.translation_queue_max,
                "backend_samples": list(self.latency_samples),
                "observer_samples": list(self.client_samples),
                "observers": [{"observer_id": sub.observer_id, **sub.diagnostics}
                              for sub in self.subscribers]}

    def report_display_drop(self, session_id, reason, count, sequence=None):
        if session_id != self.session_id:
            return
        self.display_drops += count
        self.display_drop_reasons[reason] += count
        if type(sequence) is int and 1 <= sequence <= self.sequence:
            self.affected_sequences.append(sequence)
        # Observer input is restricted to telemetry; no session mutations/captions.
        if self._telemetry_budget:
            self._telemetry_budget -= 1
            logger.warning("session=%s overlay_display_drop reason=%s count=%d",
                           session_id, reason, count)
