"""M5.2 offline timing replay; never changes application defaults or runtime services."""
import argparse
import asyncio
from collections import Counter
from dataclasses import asdict, replace
from datetime import datetime
import hashlib
import gzip
import json
import logging
import math
from pathlib import Path
import re
import statistics
import time

from app.captions.segment_manager import SegmentConfig, SegmentManager
from app.captions.terminology_normalizer import NormalizerConfig, TerminologyNormalizer
from app.environment import load_project_env
from app.translation.engine import TranslationConfig, provider_from_config
from app.translation.models import TranslationContextSegment, TranslationRequest
from replay_fixture import replay

ROOT = Path(__file__).resolve().parents[1]
A = SegmentConfig()
B = replace(A, stabilization_seconds=.6, silence_seconds=.8, minimum_words=5,
            target_words=10, max_words=18, soft_max_age_seconds=2.2, hard_max_age_seconds=4.)
C = replace(A, soft_max_age_seconds=2.5, hard_max_age_seconds=4.5)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_fixture(path):
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith(".gz") else raw)


def distribution(values):
    values = sorted(values)
    if not values:
        return None
    return {"min": values[0], "median": statistics.median(values),
            "mean": statistics.mean(values), "p95": values[math.ceil(.95 * len(values)) - 1],
            "max": values[-1]}


def final_words(events):
    snapshot = next(event["payload"] for event in reversed(events) if "lines" in event["payload"])
    return " ".join((line.get("text") or "").strip() for line in snapshot["lines"]
                    if line.get("speaker") != -2).split()


def unit_boundaries(segments, expected, units):
    """Exact annotated spans in RAW text, independent of spelling correction."""
    text = " ".join(expected)
    words = list(re.finditer(r"\S+", text))
    cuts = []
    cumulative = 0
    for index, segment in enumerate(segments[:-1], 1):
        cumulative += segment.word_count
        cuts.append((index, words[cumulative - 1].end()))
    result = []
    for unit in units:
        hits = list(re.finditer(r"(?<!\w)" + re.escape(unit) + r"(?!\w)", text))
        if len(hits) != 1:
            raise ValueError(f"Evaluation unit must match exactly once: {unit}")
        start, end = hits[0].span()
        boundaries = [index for index, cut in cuts if start < cut < end]
        result.append({"raw_unit": unit, "split_after_segments": boundaries})
    return result


def evaluate(events, config, units=(), normalize=False):
    manager = SegmentManager(config, "benchmark")
    results = list(replay(events, manager))
    segments = [segment for _, result in results for segment in result.ready_segments]
    expected, actual = final_words(events), " ".join(segment.text for segment in segments).split()
    late = [event for _, result in results for event in result.events
            if event["type"] == "late_revision_detected"]
    annotations = unit_boundaries(segments, expected, units) if actual == expected else []
    reasons = Counter(segment.reason for segment in segments)
    data = {"config": asdict(config), "ready_count": len(segments),
            "words": distribution([segment.word_count for segment in segments]),
            "latency_ms": distribution([segment.latency_ms for segment in segments]),
            "latency_without_session_end_ms": distribution([segment.latency_ms for segment in segments
                                                             if segment.reason != "session_end"]),
            "flush_reasons": dict(reasons),
            "boundary_kinds": dict(Counter(segment.boundary_kind for segment in segments)),
            "hard_age_percent": 100 * reasons["hard_max_age"] / len(segments) if segments else 0,
            "forced_whitespace_cut_count": sum(segment.boundary_kind == "whitespace" and
                segment.reason in {"soft_max_age", "hard_max_age", "max_words"} for segment in segments),
            "integrity": {"ordered_word_equality": actual == expected, "source_words": len(expected),
                "emitted_words": len(actual), "missing_words": dict(Counter(expected) - Counter(actual)),
                "excess_words": dict(Counter(actual) - Counter(expected)),
                "unique_ids": len({segment.id for segment in segments}) == len(segments),
                "pending_at_end": results[-1][1].pending_segment},
            "late_revision_count": len(late), "late_revisions": late,
            "medical_units": annotations,
            "fragmented_unit_count": sum(bool(item["split_after_segments"]) for item in annotations),
            "medical_unit_boundary_count": sum(len(item["split_after_segments"]) for item in annotations),
            "segments": [asdict(segment) for segment in segments]}
    if normalize:
        normalizer = TerminologyNormalizer.from_config(NormalizerConfig.from_env())
        for segment in data["segments"]:
            segment["normalization"] = normalizer.normalize(segment["id"], segment["text"]).to_dict()
    return data


def exploration(events, units):
    """Small, declared grid. Evaluation only: no runtime parameter selection."""
    rows = []
    for stability in (.6, .8):
        for minimum in (5, 6, 7):
            for soft, hard in ((2.2, 4.), (2.5, 4.5), (2.6, 4.8), (2.8, 4.8), (3., 5.)):
                config = replace(B, stabilization_seconds=stability, minimum_words=minimum,
                                 target_words=12, max_words=20,
                                 soft_max_age_seconds=soft, hard_max_age_seconds=hard)
                row = evaluate(events, config, units)
                rows.append({key: row[key] for key in ("config", "ready_count", "latency_ms", "words",
                             "forced_whitespace_cut_count", "fragmented_unit_count", "medical_unit_boundary_count",
                             "late_revision_count", "integrity")})
    return rows


def revision_stress_cases():
    """Synthetic boundary controls, NOT independent real-voice recordings."""
    def row(at, text):
        return {"at": at, "payload": {"lines": [{"text": text, "start": "0:00:00.00",
                "end": "0:00:01.00", "speaker": 1}], "buffer_transcription": ""}}
    return {
        "pending_correction_700ms": [row(0., "Tiene hipotensión."), row(.7, "Tiene hipertensión."),
                                     {"at": 3., "payload": {"type": "ready_to_stop"}}],
        "open_token_extended_4200ms": [row(0., "cardio"), row(4.2, "cardiovascular"),
                                       {"at": 6., "payload": {"type": "ready_to_stop"}}],
    }


def read_raw_events(path, session_id):
    """Optional full receive stream, including repeated snapshots, from existing local log."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            wrapper = json.loads(line[line.index("{"):])
            if wrapper.get("session") != session_id:
                continue
            payload = json.loads(wrapper["raw"])
            if payload.get("type") == "config":
                continue
            at = datetime.strptime(line[:23], "%Y-%m-%d %H:%M:%S,%f")
            rows.append((at, payload))
        except (ValueError, KeyError):
            continue
    if not rows:
        raise ValueError("Raw session has no messages")
    origin = rows[0][0]
    return [{"at": round((at - origin).total_seconds(), 3), "payload": payload} for at, payload in rows]


def live_evidence(paths, limit=2):
    """Join segment IDs to timing samples; deduplicate rotated/copied logs."""
    sessions = {}
    for path in paths:
        if not Path(path).exists():
            continue
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            match = re.search(r"session=(\w+) (segment_ready|caption_latency|segment normalized) (.*)", line)
            if not match:
                continue
            session, kind, value = match.groups()
            entry = sessions.setdefault(session, {"ready": {}, "stages": {}, "normalizer": {}})
            if kind == "segment_ready":
                segment = json.loads(value)
                sequence = int(segment["id"].rsplit(":", 1)[1])
                entry["ready"][sequence] = segment
                entry["last_ready_log_timestamp"] = line[:23]
            elif kind == "caption_latency":
                sequence = int(re.search(r"sequence=(\d+)", value)[1])
                entry["stages"][sequence] = json.loads(value[value.index("{"):])
            else:
                segment_id = re.search(r"id=(\S+)", value)[1]
                processing = float(re.search(r"processing_ms=([\d.]+)", value)[1])
                entry["normalizer"][int(segment_id.rsplit(":", 1)[1])] = processing
    available = [(key, entry) for key, entry in sessions.items() if entry["stages"] and entry["ready"]]
    available.sort(key=lambda item: item[1]["last_ready_log_timestamp"])
    output = []
    for session_id, entry in available[-limit:]:
        rows = []
        for sequence, segment in sorted(entry["ready"].items()):
            if sequence not in entry["stages"]:
                continue
            stage = entry["stages"][sequence]
            rows.append({"segment_id": segment["id"], "raw_text": segment["text"],
                         "asr_first_seen_s": segment["first_seen_at"], "ready_s": segment["emitted_at"],
                         "ready_reason": segment["reason"],
                         "normalization_processing_ms": entry["normalizer"].get(sequence), **stage})
        output.append({"session_id": session_id, "last_ready_log_timestamp": entry["last_ready_log_timestamp"],
                       "samples": rows, "summary": {key: distribution([row[key] for row in rows if row.get(key) is not None])
                       for key in ("asr_to_ready_ms", "ready_to_normalized_ms", "normalization_processing_ms",
                                   "provider_total_ms", "translation_queue_delay_ms", "asr_to_hub_ms")}})
    return output


def request_key(request, api_url):
    # Match provider's effective body, including context. IDs/times do not affect translation.
    body = {"api_url": api_url, "text": request.normalized_text,
            "context": " ".join(item.normalized_text for item in request.context_segments).strip(),
            "source_lang": request.source_language.upper(), "target_lang": request.target_language.upper()}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


async def compare_deepl(variants, cache_path):
    config = TranslationConfig.from_env()
    if not config.enabled or config.provider != "deepl":
        raise ValueError("Benchmark requires configured, enabled DeepL; no provider fallback")
    provider, status = provider_from_config(config)
    if provider is None:
        raise ValueError(status.message)
    cache_path = Path(cache_path)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    calls = hits = failures = characters = 0
    for label, variant in variants.items():
        previous = []
        for index, segment in enumerate(variant["segments"], 1):
            text = segment["normalization"]["normalized_text"]
            context = tuple(previous[-config.context_segments:]) if config.context_segments else ()
            request = TranslationRequest("benchmark", segment["id"], index, segment["text"], text,
                                         context, config.source_language, config.target_language, 0.)
            # Engine keeps preceding submitted inputs as context even if one fails.
            previous.append(TranslationContextSegment(segment["id"], index, text))
            key = request_key(request, config.deepl_api_url)
            if key in cache:
                hits += 1
            else:
                calls += 1
                characters += len(text)
                started = time.perf_counter()
                try:
                    translation = await provider.translate(request)
                except Exception as error:
                    failures += 1
                    segment["translation"] = {"success": False, "error_type": type(error).__name__, "request_hash": key}
                    continue  # No retries, no cached failures, no key/HTTP details printed.
                cache[key] = {"text": translation, "provider_ms": round((time.perf_counter() - started) * 1000, 3)}
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
            segment["translation"] = {"success": True, "provider": "deepl", "request_hash": key,
                                      "context": [item.normalized_text for item in context], **cache[key]}
        print(f"DeepL {label}: completed {len(variant['segments'])} inputs", flush=True)
    return {"new_requests": calls, "cache_hits": hits, "failures": failures,
            "text_characters_submitted": characters, "context_segments": config.context_segments,
            "note": "Provider durations are offline requests, not real-time end-to-end latency. Cache includes context."}


def segment_appendix(variants):
    lines = ["# M5.2 — Detalle reproducible de segmentos", "",
             "Tiempos en segundos desde el origen del fixture; RAW literal. EN procede de DeepL real si está presente.", ""]
    for label, variant in variants.items():
        lines += [f"## {label}", "", "| # | ASR first seen | READY | Latencia s | Palabras | Motivo / límite | RAW |",
                  "| --- | ---: | ---: | ---: | ---: | --- | --- |"]
        for i, segment in enumerate(variant["segments"], 1):
            text = segment["text"].replace("|", "\\|")
            lines.append(f"| {i} | {segment['first_seen_at']:.3f} | {segment['emitted_at']:.3f} | "
                         f"{segment['latency_ms']/1000:.3f} | {segment['word_count']} | {segment['reason']} / {segment['boundary_kind']} | {text} |")
        lines += ["", "### NORMALIZED → EN", ""]
        for i, segment in enumerate(variant["segments"], 1):
            translated = segment.get("translation", {}).get("text", "Not measured")
            lines.append(f"{i}. ES: {segment['normalization']['normalized_text']}  \n   EN: {translated}")
        lines += [""]
    return "\n".join(lines)


async def main():
    load_project_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "benchmarks/medical_full_receive.json.gz")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/M5_2_RESULTS.json")
    parser.add_argument("--raw-log", type=Path)
    parser.add_argument("--deepl", action="store_true", help="Real billable API calls; successful requests cached")
    parser.add_argument("--cache", type=Path, default=ROOT / "logs/m52-deepl-cache.json")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    fixture = load_fixture(args.fixture)
    annotation = ROOT / "benchmarks/medical_units.json"
    units = json.loads(annotation.read_text(encoding="utf-8"))["units"]
    # Explicit intermediate candidate; keep application defaults untouched.
    configs = {"A": A, "B": B, "C": C}
    variants = {key: evaluate(fixture["events"], value, units, normalize=True) for key, value in configs.items()}
    data = {"fixture": args.fixture.name, "fixture_sha256": digest(args.fixture),
            "annotation_sha256": digest(annotation), "event_count": len(fixture["events"]),
            "end_s": fixture["events"][-1]["at"], "percentile_method": "nearest-rank ceil(0.95*n)",
            "variants": variants, "intermediate_exploration": exploration(fixture["events"], units),
            "live_evidence": live_evidence([ROOT / "logs/development.log.1", ROOT / "logs/development.log"]),
            "synthetic_revision_controls": {name: {key: evaluate(events, value) for key, value in configs.items()}
                                            for name, events in revision_stress_cases().items()},
            "glossary_sha256": {Path(path).name: digest(path) for path in (
                NormalizerConfig.from_env().medical_glossary, NormalizerConfig.from_env().conference_glossary)}}
    sparse = load_fixture(ROOT / "benchmarks/medical_real_snapshots.json")
    data["legacy_sparse_fixture"] = {"source": "medical_real_snapshots.json", "event_count": len(sparse["events"]),
        "variants": {key: evaluate(sparse["events"], value, units) for key, value in configs.items()}}
    if args.raw_log:
        events = read_raw_events(args.raw_log, fixture["provenance"]["session_id"])
        data["full_receive_stream"] = {"source": args.raw_log.name, "sha256": digest(args.raw_log),
            "event_count": len(events), "variants": {key: evaluate(events, value, units) for key, value in configs.items()}}
    if args.deepl:
        data["deepl"] = await compare_deepl(variants, args.cache)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output.with_suffix(".md").write_text(segment_appendix(variants), encoding="utf-8")
    for label, row in variants.items():
        print(label, "READY", row["ready_count"], "latency_ms", row["latency_ms"],
              "fragmented_units", row["fragmented_unit_count"], "integrity", row["integrity"]["ordered_word_equality"])


if __name__ == "__main__":
    asyncio.run(main())
