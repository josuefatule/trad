"""Replay timed full snapshots using the exact manager and timer rules, without GPU."""
import argparse
import asyncio
from collections import Counter
from dataclasses import replace
import json
import math
from pathlib import Path
import statistics

from app.captions.segment_manager import SegmentConfig, SegmentManager
from app.captions.terminology_normalizer import NormalizerConfig, TerminologyNormalizer
from app.captions.transcript_state import TranscriptState
from app.translation import TranslationConfig, build_translation_engine


def replay(events, manager):
    state = TranscriptState()
    last = 0.
    for event in events:
        now = float(event["at"])
        if now < last:
            raise ValueError("Fixture events must be ordered by receive time")
        step = last + manager.config.tick_seconds
        while step < now - 1e-9:
            result = manager.tick(step)
            if result.ready_segments or result.events:
                yield step, result
            step += manager.config.tick_seconds
        payload = event["payload"]
        if payload.get("type") == "ready_to_stop":
            yield now, manager.finish(now)
            return
        if "lines" in payload:
            state.update(payload)
            yield now, manager.update(state, now)
        else:
            yield now, manager.tick(now)
        last = now


async def async_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--perf-repeats", type=int, default=100,
                        help="normalization performance passes over emitted READY segments")
    parser.add_argument("--translation-provider", choices=("mock", "configured", "disabled"),
                        default="mock", help="translation source for replay; mock is visibly synthetic")
    args = parser.parse_args()
    if args.perf_repeats < 0:
        parser.error("--perf-repeats must be non-negative")
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    manager = SegmentManager(SegmentConfig.from_env(), "replay")
    normalizer_config = NormalizerConfig.from_env()
    normalizer = TerminologyNormalizer.from_config(normalizer_config)
    previous = None
    late = 0
    emitted = []
    normalized = []
    translation_results = {}
    translation_requests = {}

    async def translated(result, snapshot):
        translation_results[result.segment_id] = result

    translation_config = TranslationConfig.from_env()
    if args.translation_provider == "mock":
        translation_config = replace(translation_config, enabled=True, provider="mock")
    elif args.translation_provider == "disabled":
        translation_config = replace(translation_config, enabled=False)
    translator = build_translation_engine(translation_config, "replay", translated)
    await translator.start()
    for now, result in replay(fixture["events"], manager):
        if result.pending_segment != previous:
            print(f"{now:7.3f} PENDING {result.pending_segment}")
            previous = result.pending_segment
        for segment in result.ready_segments:
            emitted.append(segment)
            print(f"{now:7.3f} READY {json.dumps(dataclass_dict(segment), ensure_ascii=False)}")
            item = normalizer.normalize(segment.id, segment.text)
            normalized.append(item)
            print(f"{now:7.3f} RAW {item.raw_text}")
            print(f"{now:7.3f} NORMALIZED {item.normalized_text}")
            for correction in item.corrections:
                print(f"{now:7.3f} CORRECTION {json.dumps(dataclass_dict(correction), ensure_ascii=False)}")
            for suggestion in item.suggestions:
                print(f"{now:7.3f} SUGGESTION {json.dumps(dataclass_dict(suggestion), ensure_ascii=False)}")
            request = await translator.submit(
                segment.id, item.raw_text, item.normalized_text,
                asr_first_seen_at=segment.first_seen_at,
                ready_at=segment.emitted_at,
                normalization_latency_ms=item.processing_ms)
            if request is not None:
                translation_requests[segment.id] = request
        for event in result.events:
            if event["type"] == "late_revision_detected":
                late += 1
                print(f"{now:7.3f} LATE {json.dumps(event, ensure_ascii=False)}")
    await translator.wait_idle()
    await translator.close()
    for index, (segment, item) in enumerate(zip(emitted, normalized), 1):
        request = translation_requests.get(segment.id)
        translated_item = translation_results.get(segment.id)
        print(f"\nSEGMENT {index:02d}")
        print(f"RAW ES:\n{item.raw_text}")
        print(f"NORMALIZED ES:\n{item.normalized_text}")
        context = ([entry.normalized_text for entry in request.context_segments]
                   if request else [])
        print("CONTEXT:\n" + json.dumps(context, ensure_ascii=False))
        if translated_item and translated_item.success:
            print(f"ENGLISH:\n{translated_item.translated_text}")
        elif translated_item:
            print(f"ENGLISH:\nERROR: {translated_item.error}")
        else:
            print("ENGLISH:\nDISABLED / MISCONFIGURED")
        print(f"PROVIDER:\n{translated_item.provider if translated_item else translator.status.provider or 'none'}")
        print("TRANSLATION LATENCY:\n{}".format(
            f"{translated_item.latency_ms:.3f} ms" if translated_item else "n/a"))

    words = [segment.word_count for segment in emitted]
    latencies = [segment.latency_ms for segment in emitted]
    reasons = Counter(segment.reason for segment in emitted)
    boundaries = Counter(segment.boundary_kind for segment in emitted)
    hard_age = reasons["hard_max_age"]
    forced_whitespace = sum(segment.boundary_kind == "whitespace"
                            and segment.reason in {"soft_max_age", "hard_max_age", "max_words"}
                            for segment in emitted)
    final_snapshot = next((event["payload"] for event in reversed(fixture["events"])
                           if "lines" in event["payload"]), {"lines": []})
    expected = " ".join((line.get("text") or "").strip()
                        for line in final_snapshot["lines"]
                        if line.get("speaker") != -2 and line.get("text")).split()
    actual = " ".join(segment.text for segment in emitted).split()
    print(f"SUMMARY segments={len(emitted)} late_revisions={late} "
          f"integrity={'PASS' if actual == expected else 'FAIL'} "
          f"source_words={len(expected)} emitted_words={len(actual)} "
          f"forced_whitespace_cut_count={forced_whitespace}")
    if emitted:
        print("WORDS min={} median={:g} mean={:.2f} max={}".format(
            min(words), statistics.median(words), statistics.mean(words), max(words)))
        print("LATENCY_MS min={:.0f} median={:.0f} mean={:.0f} max={:.0f}".format(
            min(latencies), statistics.median(latencies), statistics.mean(latencies), max(latencies)))
        print("REASONS " + " ".join(f"{reason}={count}" for reason, count in sorted(reasons.items())))
        print(f"HARD_AGE count={hard_age} percent={hard_age / len(emitted) * 100:.2f}")
        print("BOUNDARIES " + " ".join(
            f"{kind}={count}" for kind, count in sorted(boundaries.items())))
    correction_count = sum(len(item.corrections) for item in normalized)
    suggestion_count = sum(len(item.suggestions) for item in normalized)
    unchanged = sum(item.raw_text == item.normalized_text for item in normalized)
    known = sorted({term for item in normalized for term in item.known_terms})
    print(f"NORMALIZATION corrections={correction_count} suggestions={suggestion_count} "
          f"unchanged_segments={unchanged} known_terms={json.dumps(known, ensure_ascii=False)}")
    timings = []
    for _ in range(args.perf_repeats):
        measured = TerminologyNormalizer.from_config(normalizer_config)
        for segment in emitted:
            timings.append(measured.normalize(segment.id, segment.text).processing_ms)
    if timings:
        ordered = sorted(timings)
        p95 = ordered[math.ceil(len(ordered) * .95) - 1]
        print("NORMALIZER_PERF samples={} median_ms={:.3f} p95_ms={:.3f} max_ms={:.3f}".format(
            len(timings), statistics.median(timings), p95, max(timings)))
    translated_values = list(translation_results.values())
    translation_latencies = [item.latency_ms for item in translated_values]
    queue_delays = [item.queue_delay_ms for item in translated_values]
    successes = sum(item.success for item in translated_values)
    failures = len(translated_values) - successes
    print(f"TRANSLATION_SUMMARY segments={len(emitted)} successes={successes} "
          f"failures={failures} retries={translator.metrics.retries} "
          f"timeouts={translator.metrics.timeouts} max_queue_depth={translator.metrics.max_queue_depth}")
    if translation_latencies:
        print("TRANSLATION_LATENCY_MS median={:.3f} p95={:.3f} max={:.3f}".format(
            statistics.median(translation_latencies), percentile(translation_latencies, .95),
            max(translation_latencies)))
        print("TRANSLATION_QUEUE_DELAY_MS median={:.3f} p95={:.3f}".format(
            statistics.median(queue_delays), percentile(queue_delays, .95)))


def dataclass_dict(value):
    from dataclasses import asdict
    return asdict(value)


def percentile(values, quantile):
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * quantile) - 1]


if __name__ == "__main__":
    asyncio.run(async_main())
