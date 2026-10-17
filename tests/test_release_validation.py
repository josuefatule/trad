"""Release evidence invariants, including unknown clocks and exact historical inputs."""
import copy
import unittest

from benchmarks.release_validation import distribution, run_replay, summarize_pipeline
from app.captions.terminology_normalizer import NormalizerConfig, TerminologyNormalizer


class ReleaseEvidenceTests(unittest.TestCase):
    def test_negations_numbers_units_and_anatomy_survive_normalization(self):
        # Synthetic control; not evidence of recognition/translation accuracy.
        raw = "No presenta edema ni disfunción renal; dosis 5 mg, presión 120/80 mmHg, 3,5 mmol/L."
        normalizer = TerminologyNormalizer.from_config(NormalizerConfig())
        result = normalizer.normalize("control:1", raw)
        self.assertEqual(result.raw_text, raw)
        self.assertEqual(result.normalized_text, raw)
        self.assertFalse(result.corrections)

    def test_real_receive_replay_integrity_and_historical_context_match(self):
        report = run_replay()
        full = report["full_receive_A"]
        self.assertEqual(report["event_count"], 888)
        self.assertEqual(full["ready_count"], 17)
        self.assertEqual(full["integrity"]["source_words"], 81)
        self.assertTrue(full["integrity"]["ordered_word_equality"])
        self.assertEqual(full["late_revision_count"], 0)
        self.assertEqual(full["historical_translation_matches"], 17)
        self.assertEqual(full["latency_ms"]["p95"], 5539)
        self.assertEqual(full["forced_whitespace_cut_count"], 9)
        self.assertEqual(sum(len(s["normalization"]["corrections"]) for s in full["segments"]), 3)

    def test_percentiles_do_not_invent_samples_or_clamp_clock_errors(self):
        self.assertEqual(distribution([None])["n"], 0)
        self.assertIsNone(distribution([])["p95"])
        self.assertEqual(distribution(range(1, 21))["p90"], 18)
        for value in (-1, float("nan")):
            with self.assertRaises(ValueError):
                distribution([value])

    def test_correlate_session_sequence_generation_and_reject_clock_inversion(self):
        caption = {"session_id": "a", "segment_id": "a:1", "sequence": 1,
                   "visual_generation": 2, "translation_queue_depth": 0,
                   "published_mono_ms": 6100,
                   "timing": dict(zip(("asr_first_seen_mono", "ready_mono", "normalized_completed_mono",
                                       "queued_mono", "translation_started_mono", "translation_completed_mono"),
                                      (1., 4., 4.1, 4.2, 5., 6.))),
                   "latency": {"asr_to_ready_ms": 3000, "ready_to_normalized_ms": 100,
                               "translation_queue_delay_ms": 800, "provider_total_ms": 1000,
                               "translation_to_hub_ms": 100, "asr_to_hub_ms": 5100}}
        sample = {"session_id": "a", "sequence": 1, "visual_generation": 2,
                  "hub_delivery_estimate_ms": 10, "paint_delay_ms": 20}
        restored = {"session_id": "a", "sequence": 1, "visual_generation": 2}
        samples = [{**sample, "session_id": "old"}, {**sample, "visual_generation": 1}, restored, sample]
        row = summarize_pipeline([caption], samples)["rows"][0]
        self.assertEqual(row["normalized_to_translation_ms"], 1900)
        self.assertEqual(row["translation_to_paint_estimate_ms"], 130)
        self.assertIsNone(row["capture_started_mono"])
        self.assertEqual(summarize_pipeline([caption], [restored])["paint_samples_missing"], 1)
        invalid = copy.deepcopy(caption)
        invalid["timing"]["queued_mono"] = 2
        with self.assertRaises(ValueError):
            summarize_pipeline([invalid], samples)
