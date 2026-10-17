"""Conservative translation-ready segmentation of WLK full snapshots.

No ASR/model code, lexical corrections, fuzzy matching, or invented word times.
All times passed as `now` are monotonic seconds since this session began.
"""
from dataclasses import asdict, dataclass, field
import json
import logging
import math
import os
import re
import time

from app.captions.transcript_state import TranscriptState

logger = logging.getLogger("captions")


@dataclass(frozen=True)
class SegmentConfig:
    stabilization_seconds: float = .8
    silence_seconds: float = 1.0
    minimum_words: int = 7
    target_words: int = 13
    max_words: int = 21
    safe_cut_lookback_words: int = 8
    soft_max_age_seconds: float = 3.3
    hard_max_age_seconds: float = 5.5
    tick_seconds: float = .1

    def __post_init__(self):
        for name in ("stabilization_seconds", "silence_seconds", "soft_max_age_seconds",
                     "hard_max_age_seconds", "tick_seconds"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not 1 <= self.minimum_words <= self.target_words <= self.max_words:
            raise ValueError("Require 1 <= minimum_words <= target_words <= max_words")
        if self.safe_cut_lookback_words < 1:
            raise ValueError("safe_cut_lookback_words must be positive")
        if self.soft_max_age_seconds > self.hard_max_age_seconds:
            raise ValueError("soft_max_age_seconds cannot exceed hard_max_age_seconds")

    @classmethod
    def from_env(cls):
        return cls(**{
            name: cast(os.getenv(env, str(getattr(cls(), name))))
            for name, env, cast in (
                ("stabilization_seconds", "SEGMENT_STABILIZATION_SECONDS", float),
                ("silence_seconds", "SEGMENT_SILENCE_SECONDS", float),
                ("minimum_words", "SEGMENT_MINIMUM_WORDS", int),
                ("target_words", "SEGMENT_TARGET_WORDS", int),
                ("max_words", "SEGMENT_MAX_WORDS", int),
                ("safe_cut_lookback_words", "SEGMENT_SAFE_CUT_LOOKBACK_WORDS", int),
                ("soft_max_age_seconds", "SEGMENT_SOFT_MAX_AGE_SECONDS", float),
                ("hard_max_age_seconds", "SEGMENT_HARD_MAX_AGE_SECONDS", float),
                ("tick_seconds", "SEGMENT_TICK_SECONDS", float),
            )
        })


@dataclass(frozen=True)
class CaptionSegment:
    id: str
    text: str
    start_time: float | None
    end_time: float | None
    emitted_at: float
    reason: str
    boundary_kind: str
    first_seen_at: float
    latency_ms: float
    word_count: int
    revisions_before_ready: int
    source_ids: tuple[str, ...]
    timing_precision: str = "source_line_bounds"


@dataclass(frozen=True)
class SegmentResult:
    confirmed_text: str
    pending_segment: str
    ready_segments: tuple[CaptionSegment, ...]
    events: tuple[dict, ...]

    def to_dict(self):
        return asdict(self)


@dataclass
class _Source:
    id: str
    text: str
    start: float | None
    end: float | None
    first_seen: list[float]
    changed_at: list[float]
    consumed: int = 0
    published_ids: list[str] = field(default_factory=list)


def timestamp(value):
    """WLK H:MM:SS.cc -> audio seconds; absent/invalid times remain unknown."""
    if value is None:
        return None
    try:
        parts = str(value).split(":")
        result = float(parts[-1])
        if len(parts) == 3:
            result += int(parts[0]) * 3600 + int(parts[1]) * 60
        elif len(parts) != 1:
            return None
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def _edges(old, new):
    """Exact common prefix/suffix only; no approximate text matching."""
    prefix = 0
    while prefix < min(len(old), len(new)) and old[prefix] == new[prefix]:
        prefix += 1
    suffix = 0
    while (suffix < min(len(old), len(new)) - prefix
           and old[len(old) - suffix - 1] == new[len(new) - suffix - 1]):
        suffix += 1
    return prefix, suffix


class SegmentManager:
    def __init__(self, config=None, session_id="session"):
        self.config = config or SegmentConfig()
        self.session_id = session_id
        self.reset()

    def reset(self):
        self._origin = time.monotonic()
        self._last_now = 0.
        self._sources = []
        self._active = []
        self._layout = []
        self._emitted = []
        self._confirmed = ""
        self._last_pending = ""
        self._revisions = 0
        self._events = []
        self._ended = False
        logger.info("session=%s segment_manager_reset", self.session_id)

    @property
    def emitted_segments(self):
        return tuple(self._emitted)

    @property
    def monotonic_origin(self):
        """Clock anchor for stage diagnostics; segmentation decisions are unchanged."""
        return self._origin

    def _now(self, now):
        now = time.monotonic() - self._origin if now is None else now
        if not math.isfinite(now) or now < self._last_now:
            raise ValueError("now must be finite and monotonic")
        self._last_now = now
        return now

    def _event(self, kind, **values):
        event = {"type": kind, **values}
        self._events.append(event)
        logger.info("session=%s %s %s", self.session_id, kind, json.dumps(event, ensure_ascii=False))

    def _late(self, source, old_text, new_text, old_times, new_times, **extra):
        self._event("late_revision_detected", source_id=source.id,
                    segment_ids=list(source.published_ids), old_text=old_text,
                    new_text=new_text, old_timestamps=old_times,
                    new_timestamps=new_times, **extra)

    def _reconcile(self, source, text, start, end, now):
        old, cut = source.text, source.consumed
        prefix, suffix = _edges(old, text)
        old_stop, new_stop = len(old) - suffix, len(text) - suffix
        if cut and cut == len(old) and text.startswith(old) and len(text) > cut and not text[cut].isspace():
            # A published terminal token was later extended (arter -> arterial)
            # or punctuated. Never emit its detached suffix as a new segment.
            mapped = cut
            while mapped < len(text) and not text[mapped].isspace():
                mapped += 1
            self._late(source, old[:cut], text[:mapped],
                       [source.start, source.end], [start, end], token_extended=True)
            source.consumed = mapped
        elif cut and prefix < cut:
            # Map the consumed boundary across ONE exact changed interval.
            # If it crosses the boundary, quarantine the ambiguous changed region.
            mapped = cut + len(text) - len(old) if cut >= old_stop else new_stop
            mapped = max(0, min(len(text), mapped))
            self._late(source, old[:cut], text[:mapped],
                       [source.start, source.end], [start, end],
                       boundary_crossed=cut < old_stop)
            source.consumed = mapped
        # A changed start is a retiming. Extending an end with NEW text is normal.
        if cut and (start != source.start or (old == text and end != source.end)):
            self._late(source, old[:cut], text[:source.consumed],
                       [source.start, source.end], [start, end], retimed=True)
        source.first_seen = (source.first_seen[:prefix] + [now] * (new_stop - prefix)
                             + (source.first_seen[len(old) - suffix:] if suffix else []))
        source.changed_at = (source.changed_at[:prefix] + [now] * (new_stop - prefix)
                             + (source.changed_at[len(old) - suffix:] if suffix else []))
        source.text, source.start, source.end = text, start, end
        if source.consumed:
            while source.consumed < len(text) and text[source.consumed].isspace():
                source.consumed += 1

    def update(self, transcript: TranscriptState, now=None):
        if self._ended:
            raise RuntimeError("Session ended; reset before applying a new snapshot")
        now = self._now(now)
        self._events = []
        self._confirmed = transcript.confirmed_text
        previous, active, used, layout = self._active, [], set(), []
        # Retain exact fully consumed spans before mutating a line that WLK splits.
        covered = [(s.text, s.start, s.end, list(s.published_ids)) for s in previous
                   if s.consumed == len(s.text) and s.consumed]
        for line in transcript.segments:
            start, end = timestamp(line.get("start")), timestamp(line.get("end"))
            if line.get("speaker") == -2:
                layout.append((None, start, end))
                continue
            text = (line.get("text") or "").strip()
            if not text:
                continue
            # Start + occurrence identifies ordered lines; speaker labels may change.
            source = next((s for s in self._sources if start is not None
                           and s.start == start and s.id not in used), None)
            if source is None and len(active) < len(previous):
                candidate = previous[len(active)]
                overlap = (None not in (start, end, candidate.start, candidate.end)
                           and max(start, candidate.start) < min(end, candidate.end))
                if candidate.id not in used and (start is None or candidate.start is None or overlap):
                    source = candidate
            if source is None:
                source = _Source(f"source-{len(self._sources) + 1}", text, start, end,
                                 [now] * len(text), [now] * len(text))
                self._sources.append(source)
                for old_text, old_start, old_end, ids in covered:
                    contained_time = (None not in (start, end, old_start, old_end)
                                      and old_start <= start <= end <= old_end)
                    occurrences = list(re.finditer(r"(?<!\w)" + re.escape(text) + r"(?!\w)", old_text))
                    if contained_time and len(occurrences) == 1:
                        source.consumed = len(text)
                        source.published_ids = ids
                        self._late(source, old_text, text, [old_start, old_end],
                                   [start, end], resegmented=True)
                        break
            else:
                self._reconcile(source, text, start, end, now)
            used.add(source.id)
            active.append(source)
            layout.append((source, start, end))
        for source in previous:
            if source.id not in used and source.consumed:
                self._late(source, source.text[:source.consumed], "",
                           [source.start, source.end], [None, None], removed=True)
        self._active, self._layout = active, layout
        return self._evaluate(now)

    def tick(self, now=None):
        self._events = []
        return self._evaluate(self._now(now))

    def finish(self, now=None):
        """Call only after WLK ready_to_stop, never at browser's audio EOF."""
        self._events = []
        result = self._evaluate(self._now(now), final=True)
        self._ended = True
        return result

    def _pending(self):
        text, refs, pauses, line_cuts = "", [], [], []
        previous_end = None
        for source, start, end in self._layout:
            if source is None:
                if text and start is not None and end is not None:
                    pauses.append((len(text), max(0., end - start)))
                continue
            tail = source.text[source.consumed:]
            if not tail.strip():
                previous_end = end
                continue
            if text:
                line_cuts.append(len(text))
                if start is not None and previous_end is not None:
                    pauses.append((len(text), max(0., start - previous_end)))
                text += " "
                refs.append(None)
            # Cursor consumes whitespace too; keep all intra-line spelling intact.
            offset = source.consumed
            text += tail
            refs.extend((source, i) for i in range(offset, len(source.text)))
            previous_end = end
        return text, refs, pauses, line_cuts

    def _stable(self, refs, cut, now):
        actual = [r for r in refs[:cut] if r is not None]
        return actual and now - max(s.changed_at[i] for s, i in actual) >= self.config.stabilization_seconds

    def _safe_cut(self, text, refs, line_cuts, now, *, allow_whitespace,
                  minimum_whitespace_words=1, require_stability=True):
        """Find the best eligible boundary while looking backward from the target."""
        words = list(re.finditer(r"\S+", text))
        complete = [w for w in words if w.end() < len(text) and text[w.end()].isspace()]
        if not complete:
            return 0, None
        anchor = min(len(complete), self.config.target_words)
        lower = max(1, anchor - self.config.safe_cut_lookback_words + 1)
        candidates = []
        line_cuts = set(line_cuts)
        for word_number in range(lower, anchor + 1):
            cut = complete[word_number - 1].end()
            if require_stability and not self._stable(refs, cut, now):
                continue
            token = complete[word_number - 1].group()
            if re.search(r"[.!?]+$", token):
                priority, kind = 0, "strong_punctuation"
            elif token.endswith(";"):
                priority, kind = 1, "semicolon"
            elif token.endswith(","):
                priority, kind = 2, "comma"
            elif cut in line_cuts:
                priority, kind = 3, "line"
            elif allow_whitespace:
                if word_number < minimum_whitespace_words:
                    continue
                priority, kind = 4, "whitespace"
            else:
                continue
            candidates.append((priority, -word_number, cut, kind))
        if not candidates:
            return 0, None
        _, _, cut, kind = min(candidates)
        return cut, kind

    def _natural_target_cut(self, text, refs, line_cuts, now):
        """At target length, emit only when a useful weak boundary exists."""
        if len(text.split()) < self.config.target_words:
            return 0, None
        return self._safe_cut(text, refs, line_cuts, now, allow_whitespace=False)

    def _choose(self, text, refs, pauses, line_cuts, now):
        for match in re.finditer(r"[.!?]+(?=\s|$)", text):
            if len(text[:match.end()].split()) <= self.config.max_words and self._stable(refs, match.end(), now):
                return match.end(), "punctuation", "strong_punctuation"
            # Preserve sentence order; do not bypass an unstable first sentence.
            break
        for cut, duration in pauses:
            useful = (len(text[:cut].split()) >= self.config.minimum_words
                      or bool(re.search(r"[.!?]+\s*$", text[:cut])))
            if (duration >= self.config.silence_seconds and useful
                    and len(text[:cut].split()) <= self.config.max_words
                    and self._stable(refs, cut, now)):
                return cut, "silence", "line"
        target_cut, target_kind = self._natural_target_cut(text, refs, line_cuts, now)
        if target_cut and self._stable(refs, target_cut, now):
            return target_cut, "target_words", target_kind
        word_count = len(text.split())
        if word_count >= self.config.max_words:
            # Strong bound: ASR-confirmed complete words may flush without
            # waiting for the stabilization timer.
            cut, kind = self._safe_cut(
                text, refs, line_cuts, now, allow_whitespace=True,
                minimum_whitespace_words=self.config.minimum_words,
                require_stability=False)
            if cut:
                return cut, "max_words", kind
        if refs:
            first = min(s.first_seen[i] for r in refs if r is not None for s, i in [r])
            age = now - first
            if age >= self.config.hard_max_age_seconds:
                cut, kind = self._safe_cut(text, refs, line_cuts, now, allow_whitespace=True)
                if cut:
                    return cut, "hard_max_age", kind
                return len(text), "hard_max_age", "whitespace"
            if age >= self.config.soft_max_age_seconds and word_count >= self.config.minimum_words:
                cut, kind = self._safe_cut(
                    text, refs, line_cuts, now, allow_whitespace=True,
                    minimum_whitespace_words=self.config.minimum_words)
                if cut:
                    return cut, "soft_max_age", kind
        return 0, None, None

    def _emit(self, text, refs, cut, reason, boundary_kind, now):
        consumed_refs = [r for r in refs[:cut] if r is not None]
        sources = list({s.id: s for s, _ in consumed_refs}.values())
        first = min(s.first_seen[i] for s, i in consumed_refs)
        start, end = sources[0].start, sources[-1].end
        segment = CaptionSegment(
            id=f"{self.session_id}:{len(self._emitted) + 1}", text=text[:cut].strip(),
            start_time=start, end_time=end, emitted_at=now, reason=reason,
            boundary_kind=boundary_kind,
            first_seen_at=first, latency_ms=round((now - first) * 1000, 3),
            word_count=len(text[:cut].split()), revisions_before_ready=self._revisions,
            source_ids=tuple(s.id for s in sources))
        for source, index in consumed_refs:
            source.consumed = max(source.consumed, index + 1)
        for source in sources:
            while source.consumed < len(source.text) and source.text[source.consumed].isspace():
                source.consumed += 1
            source.published_ids.append(segment.id)
        self._emitted.append(segment)
        self._event("segment_ready", **asdict(segment), flush_reason=reason)
        self._revisions = 0
        return segment

    def _evaluate(self, now, final=False):
        text, refs, pauses, line_cuts = self._pending()
        if text != self._last_pending:
            if self._last_pending and not text.startswith(self._last_pending):
                self._revisions += 1
            self._event("segment_pending_updated", text=text, observed_at=now,
                        revisions=self._revisions)
        ready = []
        while text.strip() and not self._ended:
            cut, reason, boundary_kind = ((len(text), "session_end", "session_end") if final
                                          else self._choose(text, refs, pauses, line_cuts, now))
            if not cut:
                break
            ready.append(self._emit(text, refs, cut, reason, boundary_kind, now))
            text, refs, pauses, line_cuts = self._pending()
            self._event("segment_pending_updated", text=text, observed_at=now,
                        revisions=self._revisions)
        self._last_pending = text
        return SegmentResult(self._confirmed, text, tuple(ready), tuple(self._events))
