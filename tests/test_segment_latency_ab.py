"""Reproducible timing/quality evaluation; never sends real translation requests."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.captions.segment_manager import SegmentConfig
from app.translation.engine import TranslationConfig, TranslationStatus
from app.translation.models import TranslationContextSegment, TranslationRequest
from benchmarks.segment_latency_ab import (A, B, C, ROOT, compare_deepl, distribution, evaluate,
                                          live_evidence, load_fixture, request_key, revision_stress_cases,
                                          unit_boundaries)


class SegmentBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((ROOT / "benchmarks/medical_real_snapshots.json").read_text(encoding="utf-8"))
        cls.units = json.loads((ROOT / "benchmarks/medical_units.json").read_text(encoding="utf-8"))["units"]

    def test_original_timed_fixture_ab_integrity_and_quality_regression(self):
        before = json.dumps(self.fixture, sort_keys=True)
        self.assertEqual(A, SegmentConfig())  # No deployment/default changes.
        a = evaluate(self.fixture["events"], A, self.units)
        b = evaluate(self.fixture["events"], B, self.units)
        for row in (a, b):
            self.assertTrue(row["integrity"]["ordered_word_equality"])
            self.assertEqual(row["integrity"]["source_words"], 81)
            self.assertEqual(row["integrity"]["emitted_words"], 81)
            self.assertEqual(row["integrity"]["excess_words"], {})
            self.assertEqual(row["integrity"]["missing_words"], {})
            self.assertTrue(row["integrity"]["unique_ids"])
            self.assertEqual(row["integrity"]["pending_at_end"], "")
            self.assertEqual(row["late_revision_count"], 0)
        self.assertEqual((a["ready_count"], b["ready_count"]), (16, 22))
        self.assertEqual((a["latency_ms"]["median"], b["latency_ms"]["median"]), (3825.5, 3116.))
        self.assertEqual((a["latency_ms"]["p95"], b["latency_ms"]["p95"]), (5598., 4068.))
        self.assertEqual((a["forced_whitespace_cut_count"], b["forced_whitespace_cut_count"]), (8, 14))
        self.assertEqual((a["fragmented_unit_count"], b["fragmented_unit_count"]), (5, 9))
        self.assertEqual((a["medical_unit_boundary_count"], b["medical_unit_boundary_count"]), (5, 11))
        self.assertEqual(json.dumps(self.fixture, sort_keys=True), before)

    def test_p95_uses_nearest_rank_not_interpolation(self):
        self.assertEqual(distribution(list(range(1, 23)))["p95"], 21)
        self.assertEqual(distribution([5])["p95"], 5)
        self.assertIsNone(distribution([]))

    def test_complete_original_receive_stream_and_intermediate_candidate(self):
        fixture = load_fixture(ROOT / "benchmarks/medical_full_receive.json.gz")
        self.assertEqual(len(fixture["events"]), 888)
        self.assertEqual(fixture["events"][-1]["at"], 58.3)
        self.assertEqual(fixture["provenance"]["session_id"], self.fixture["provenance"]["session_id"])
        # Every historical selected payload/time still occurs unmodified in full capture.
        for event in self.fixture["events"]:
            self.assertIn(event, fixture["events"])
        rows = [evaluate(fixture["events"], config, self.units) for config in (A, B, C)]
        self.assertEqual([row["ready_count"] for row in rows], [17, 22, 17])
        self.assertEqual([row["latency_ms"]["median"] for row in rows], [3751., 3107.5, 3940.])
        self.assertEqual([row["latency_ms"]["p95"] for row in rows], [5539., 4061., 4550.])
        self.assertEqual([row["forced_whitespace_cut_count"] for row in rows], [9, 14, 9])
        self.assertEqual([row["fragmented_unit_count"] for row in rows], [5, 9, 5])
        for row in rows:
            self.assertTrue(row["integrity"]["ordered_word_equality"])
            self.assertEqual(row["late_revision_count"], 0)

    def test_annotation_detects_internal_boundary_only(self):
        rows = [SimpleNamespace(word_count=2), SimpleNamespace(word_count=2), SimpleNamespace(word_count=1)]
        result = unit_boundaries(rows, "uno dos tres cuatro cinco".split(), ["dos tres", "tres cuatro"])
        self.assertEqual(result[0]["split_after_segments"], [1])
        self.assertEqual(result[1]["split_after_segments"], [])
        with self.assertRaises(ValueError):
            unit_boundaries(rows, "uno dos tres cuatro cinco".split(), ["not present"])

    def test_lower_thresholds_expose_revision_risk_without_mutating_ready(self):
        for name, events in revision_stress_cases().items():
            with self.subTest(case=name):
                for config in (A, C):
                    row = evaluate(events, config)
                    self.assertTrue(row["integrity"]["ordered_word_equality"])
                    self.assertEqual(row["late_revision_count"], 0)
                row = evaluate(events, B)
                self.assertFalse(row["integrity"]["ordered_word_equality"])
                self.assertEqual(row["late_revision_count"], 1)
                # Immutable READY deliberately preserves the old ASR token.
                self.assertIn(row["segments"][0]["text"], ("Tiene hipotensión.", "cardio"))

    def test_live_stage_join_is_by_session_sequence_and_deduplicates(self):
        segment = {"id": "live:2", "text": "Real text.", "first_seen_at": 1., "emitted_at": 4.,
                   "reason": "soft_max_age"}
        stages = {"asr_to_ready_ms": 3000., "ready_to_normalized_ms": 10.,
                  "provider_total_ms": 500., "translation_queue_delay_ms": 0., "asr_to_hub_ms": 3510.}
        lines = ["2026-10-17 00:00:04,000 INFO session=live segment_ready " + json.dumps(segment),
                 "2026-10-17 00:00:04,010 INFO session=live segment normalized id=live:2 corrections=0 suggestions=0 processing_ms=9.5",
                 "2026-10-17 00:00:04,510 INFO session=live caption_latency sequence=2 " + json.dumps(stages)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.log"
            path.write_text("\n".join(lines), encoding="utf-8")
            row = live_evidence([path, path])[0]
        self.assertEqual(len(row["samples"]), 1)
        self.assertEqual(row["samples"][0]["segment_id"], "live:2")
        self.assertEqual(row["summary"]["asr_to_ready_ms"]["median"], 3000.)
        self.assertEqual(row["samples"][0]["normalization_processing_ms"], 9.5)


class TranslationCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_reuses_identical_effective_requests_including_context(self):
        requests = []
        class Provider:
            async def translate(self, request):
                requests.append(request)
                return "English " + request.normalized_text
        config = TranslationConfig(enabled=True, provider="deepl", context_segments=2, deepl_auth_key="test-only")
        def variant():
            return {"segments": [{"id": f"bench:{i}", "text": text,
                                  "normalization": {"normalized_text": text}}
                                 for i, text in enumerate(("Primera.", "Segunda."), 1)]}
        with tempfile.TemporaryDirectory() as directory, \
                patch("benchmarks.segment_latency_ab.TranslationConfig.from_env", return_value=config), \
                patch("benchmarks.segment_latency_ab.provider_from_config", return_value=(
                    Provider(), TranslationStatus("ready", "deepl", "test"))):
            cache = Path(directory) / "cache.json"
            result = await compare_deepl({"A": variant(), "B": variant()}, cache)
            self.assertEqual((result["new_requests"], result["cache_hits"]), (2, 2))
            self.assertEqual(len(requests), 2)
            again = await compare_deepl({"A": variant()}, cache)
            self.assertEqual((again["new_requests"], again["cache_hits"]), (0, 2))
            self.assertNotIn("test-only", cache.read_text(encoding="utf-8"))
        request = requests[1]
        changed = replace(request, context_segments=(TranslationContextSegment("different", 1, "Other context"),))
        self.assertNotEqual(request_key(request, "endpoint"), request_key(changed, "endpoint"))
        self.assertEqual(request_key(request, "endpoint"), request_key(replace(request, sequence=99), "endpoint"))
