"""One-process monotonic stage timestamps; never mix these with browser clocks."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TranslationTiming:
    asr_first_seen_mono: float | None = None
    ready_mono: float | None = None
    normalized_completed_mono: float | None = None
    queued_mono: float | None = None
    translation_started_mono: float | None = None
    translation_completed_mono: float | None = None
    provider_attempts_ms: tuple[float, ...] = ()


def elapsed_ms(start, end):
    return round(max(0., end - start) * 1000, 3) if None not in (start, end) else None


def stage_durations(timing, published_mono):
    if timing is None:
        return {}
    return {
        "asr_to_ready_ms": elapsed_ms(timing.asr_first_seen_mono, timing.ready_mono),
        "ready_to_normalized_ms": elapsed_ms(timing.ready_mono, timing.normalized_completed_mono),
        "ready_to_translation_started_ms": elapsed_ms(timing.ready_mono, timing.translation_started_mono),
        "translation_queue_delay_ms": elapsed_ms(timing.queued_mono, timing.translation_started_mono),
        "provider_total_ms": elapsed_ms(timing.translation_started_mono, timing.translation_completed_mono),
        "provider_last_attempt_ms": timing.provider_attempts_ms[-1] if timing.provider_attempts_ms else None,
        "translation_to_hub_ms": elapsed_ms(timing.translation_completed_mono, published_mono),
        "ready_to_hub_ms": elapsed_ms(timing.ready_mono, published_mono),
        "asr_to_hub_ms": elapsed_ms(timing.asr_first_seen_mono, published_mono),
    }
