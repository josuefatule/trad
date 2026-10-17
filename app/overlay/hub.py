"""One active publisher, many bounded read-only subscribers, one event loop."""
import asyncio
from dataclasses import dataclass, field
import logging
import time

logger = logging.getLogger("captions")


@dataclass(eq=False)
class Subscriber:
    queue: asyncio.Queue
    closed: asyncio.Event = field(default_factory=asyncio.Event)


class CaptionHub:
    protocol_version = 1

    def __init__(self, config, *, subscriber_limit=32, queue_size=64, clock=time.time):
        self.config = config
        self.subscriber_limit = subscriber_limit
        self.queue_size = queue_size
        self.clock = clock
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
        self.translator_state = "unknown"
        self._telemetry_budget = 20

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
        if caption and (caption["expires_at"] <= self.clock()
                        or self.state in {"waiting", "connecting", "disconnected", "error"}):
            caption = None
        return {"type": "snapshot", "protocol_version": self.protocol_version,
                "event_id": self.event_id, "session_id": self.session_id,
                "state": self.state, "sequence": self.sequence,
                "translator_state": self.translator_state,
                "caption": caption, "server_time": self.clock()}

    def subscribe(self):
        if len(self.subscribers) >= self.subscriber_limit:
            raise ValueError("Overlay subscriber limit reached")
        subscriber = Subscriber(asyncio.Queue(maxsize=self.queue_size))
        # Synchronous atomic registration + snapshot: no await/race between them.
        self.subscribers.add(subscriber)
        subscriber.queue.put_nowait(self.snapshot())
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
        self.translator_state = "unknown"
        self.state = "connecting"
        self._event("session", state=self.state)

    def set_state(self, session_id, state):
        if session_id != self.session_id:
            self.stale_events += 1
            return
        self.state = state
        if state in {"disconnected", "error"}:
            self.last_caption = None
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
            self._event("translator", state="invalid_caption", sequence=result.sequence)
            logger.warning("session=%s overlay_caption_rejected sequence=%d", self.session_id, result.sequence)
            return False
        self.translator_state = "ready"
        now = self.clock()
        self.last_caption = {"session_id": result.session_id, "sequence": result.sequence,
                             "segment_id": result.segment_id, "text": text,
                             "provider": result.provider, "published_at": now,
                             "expires_at": now + self.config.max_display_ms / 1000}
        self._event("caption", caption=self.last_caption)
        return True

    def diagnostics(self):
        return {"session_id": self.session_id, "state": self.state,
                "overlay_connections": len(self.subscribers),
                "last_caption": self.last_caption,
                "broadcast_errors": self.broadcast_errors,
                "stale_events": self.stale_events, "filtered_mock": self.filtered_mock,
                "display_drops": self.display_drops, "translator_state": self.translator_state}

    def report_display_drop(self, session_id, reason, count):
        if session_id != self.session_id:
            return
        self.display_drops += count
        # Observer input is restricted to telemetry; no session mutations/captions.
        if self._telemetry_budget:
            self._telemetry_budget -= 1
            logger.warning("session=%s overlay_display_drop reason=%s count=%d",
                           session_id, reason, count)
