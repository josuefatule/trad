"""Immutable inputs and outputs at the translation boundary."""
from dataclasses import asdict, dataclass
from .timing import TranslationTiming


@dataclass(frozen=True)
class TranslationContextSegment:
    segment_id: str
    sequence: int
    normalized_text: str


@dataclass(frozen=True)
class TranslationRequest:
    session_id: str
    segment_id: str
    sequence: int
    raw_text: str
    normalized_text: str
    context_segments: tuple[TranslationContextSegment, ...]
    source_language: str
    target_language: str
    queued_at: float
    asr_first_seen_at: float | None = None
    ready_at: float | None = None
    normalization_latency_ms: float | None = None
    timing: TranslationTiming | None = None
    terminology_context: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class TranslationResult:
    session_id: str
    segment_id: str
    sequence: int
    raw_text: str
    normalized_text: str
    translated_text: str | None
    provider: str
    success: bool
    error: str | None
    attempt_count: int
    queued_at: float
    started_at: float
    completed_at: float
    queue_delay_ms: float
    latency_ms: float
    asr_first_seen_at: float | None = None
    ready_at: float | None = None
    normalization_latency_ms: float | None = None
    timing: TranslationTiming | None = None
    source_language: str = "es"
    target_language: str = "en"

    def to_dict(self):
        return asdict(self)
