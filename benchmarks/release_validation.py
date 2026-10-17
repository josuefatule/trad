"""M8 offline evidence. No environment loading, network requests or runtime changes.

python -m benchmarks.release_validation --output benchmarks/m8_replay_results.json
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics

from app.captions.terminology_normalizer import NormalizerConfig, TerminologyNormalizer
from benchmarks.segment_latency_ab import (
    A, ROOT, digest, evaluate, load_fixture, revision_stress_cases,
)


def distribution(values):
    values = sorted(value for value in values if value is not None)
    if not values:
        return {"n": 0, "median": None, "p90": None, "p95": None, "max": None}
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("Invalid duration; do not silently clamp a clock error")
    return {"n": len(values), "min": values[0], "median": statistics.median(values),
            "mean": statistics.mean(values),
            "p90": values[math.ceil(.90 * len(values)) - 1],
            "p95": values[math.ceil(.95 * len(values)) - 1], "max": values[-1]}


def summarize_pipeline(captions, observer_samples):
    """One process monotonic backend clock + existing explicit WS clock calibration.

    Test publications include generation. Restored snapshots have no calibrated
    delivery and are excluded. Select first measured observer per publication;
    never count CLEAR or reconnect restoration as a new translation.
    """
    rows = []
    for caption in captions:
        timing = caption["timing"]
        names = ("asr_first_seen_mono", "ready_mono", "normalized_completed_mono",
                 "queued_mono", "translation_started_mono", "translation_completed_mono")
        stamps = [timing.get(name) for name in names] + [caption["published_mono_ms"] / 1000]
        known = [value for value in stamps if value is not None]
        if any(not math.isfinite(value) for value in known) or any(
                end < start for start, end in zip(known, known[1:])):
            raise ValueError("Backend timestamps are unordered or use unrelated clocks")
        sample = next((sample for sample in observer_samples
                       if sample["session_id"] == caption["session_id"]
                       and sample["sequence"] == caption["sequence"]
                       and sample.get("visual_generation", 0) == caption["visual_generation"]
                       and "hub_delivery_estimate_ms" in sample
                       and "paint_delay_ms" in sample), None)
        normalized, completed = stamps[2], stamps[5]
        row = {"session_id": caption["session_id"], "segment_id": caption["segment_id"],
               "sequence": caption["sequence"], "visual_generation": caption["visual_generation"],
               "backend_clock": "time.monotonic seconds in isolated ASGI process",
               "timing": timing, "published_mono_ms": caption["published_mono_ms"],
               **caption["latency"], "translation_queue_depth": caption["translation_queue_depth"],
               "normalized_to_translation_ms": None if normalized is None or completed is None
               else round((completed - normalized) * 1000, 3),
               "capture_started_mono": None, "first_partial_seen_mono": None,
               "first_confirmed_seen_mono": timing.get("asr_first_seen_mono"),
               "observer": sample,
               "translation_to_paint_estimate_ms": None if sample is None else round(
                   caption["latency"]["translation_to_hub_ms"] +
                   sample["hub_delivery_estimate_ms"] + sample["paint_delay_ms"], 3)}
        rows.append(row)
    metrics = ("asr_to_ready_ms", "ready_to_normalized_ms", "normalized_to_translation_ms",
               "translation_queue_delay_ms", "provider_total_ms", "translation_to_hub_ms",
               "asr_to_hub_ms", "translation_to_paint_estimate_ms")
    return {"rows": rows, "summary_ms": {name: distribution([row[name] for row in rows])
                                           for name in metrics},
            "paint_samples_missing": sum(row["observer"] is None for row in rows),
            "queue_depth_at_publish": distribution([row["translation_queue_depth"] for row in rows])}


def run_replay():
    fixture = ROOT / "benchmarks/medical_full_receive.json.gz"
    data = load_fixture(fixture)
    units = load_fixture(ROOT / "benchmarks/medical_units.json")["units"]
    result = evaluate(data["events"], A, units)
    normalizer = TerminologyNormalizer.from_config(NormalizerConfig())
    historical = load_fixture(ROOT / "benchmarks/M5_2_RESULTS.json")
    matches = (historical["fixture_sha256"] == digest(fixture)
               and historical["variants"]["A"]["config"] == asdict(A)
               and all(historical["glossary_sha256"][name] == digest(ROOT / "glossaries" / name)
                       for name in ("medical_base.json", "conference.json")))
    previous = []
    for index, segment in enumerate(result["segments"]):
        normalized = normalizer.normalize(segment["id"], segment["text"]).to_dict()
        segment["normalization"] = normalized
        old = historical["variants"]["A"]["segments"][index]
        translation = old.get("translation", {})
        # Historical English is admissible only for identical input and context.
        exact = (matches and old["text"] == segment["text"] and
                 old["normalization"]["normalized_text"] == normalized["normalized_text"] and
                 translation.get("context") == previous[-2:])
        segment["historical_translation"] = translation if exact else None
        previous.append(normalized["normalized_text"])
        segment["clock_domain"] = "original WLK receive offsets, virtual replay seconds"
        segment["first_partial_seen_at"] = None
        segment["first_confirmed_seen_at"] = segment["first_seen_at"]
        segment["audio_bounds_precision"] = "source_line_bounds, not word timestamps"
    result["latency_ms"] = distribution([s["latency_ms"] for s in result["segments"]])
    # CPU processing has a different clock from the virtual replay. Never add them.
    result["normalizer_processing_ms_separate_clock"] = distribution([
        s["normalization"]["processing_ms"] for s in result["segments"]])
    result["ready_per_minute"] = len(result["segments"]) * 60 / data["events"][-1]["at"]
    result["latency_trajectory_ms"] = {
        name: distribution([s["latency_ms"] for s in result["segments"][start:end]])
        for name, start, end in (("first_third", 0, 6), ("middle_third", 6, 12), ("last_third", 12, 17))}
    result["historical_translation_matches"] = sum(
        s["historical_translation"] is not None for s in result["segments"])
    sparse = load_fixture(ROOT / "benchmarks/medical_real_snapshots.json")
    return {"schema_version": 1, "generated_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "offline replay A; no DeepL calls; historical English explicitly labeled",
            "fixture": str(fixture.relative_to(ROOT)), "fixture_sha256": digest(fixture),
            "historical_evidence_sha256": digest(ROOT / "benchmarks/M5_2_RESULTS.json"),
            "event_count": len(data["events"]), "duration_s": data["events"][-1]["at"],
            "percentile_method": "nearest rank ceil(p*n); median conventional",
            "full_receive_A": result,
            "sparse_same_recording_A": evaluate(sparse["events"], A, units),
            "synthetic_controls": {name: evaluate(events, A)
                                   for name, events in revision_stress_cases().items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_replay()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "ready": report["full_receive_A"]["ready_count"],
                      "integrity": report["full_receive_A"]["integrity"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
