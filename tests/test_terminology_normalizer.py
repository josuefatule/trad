import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from app.captions.segment_manager import SegmentManager
from app.captions.terminology_normalizer import NormalizerConfig, TerminologyNormalizer
from replay_fixture import replay


class TerminologyNormalizerTests(unittest.TestCase):
    def setUp(self):
        self.normalizer = TerminologyNormalizer.from_config(NormalizerConfig())

    def test_exact_variant_preserves_raw_and_is_auditable(self):
        result = self.normalizer.normalize("s:1", "Presión systólica estable.")
        self.assertEqual(result.raw_text, "Presión systólica estable.")
        self.assertEqual(result.normalized_text, "Presión sistólica estable.")
        self.assertEqual(len(result.corrections), 1)
        correction = result.corrections[0]
        self.assertEqual((correction.source, correction.replacement,
                          correction.start, correction.end, correction.rule),
                         ("systólica", "sistólica", 8, 17, "exact_variant"))
        self.assertEqual(correction.confidence, 1.)

    def test_accents_and_case_normalization(self):
        result = self.normalizer.normalize("s:1", "PRESIÓN SYSTOLICA")
        self.assertEqual(result.normalized_text, "PRESIÓN SISTÓLICA")

    def test_hyphen_space_equivalence_and_multiword_term(self):
        result = self.normalizer.normalize("s:1", "Renina angiotensina aldosterona")
        self.assertEqual(result.normalized_text, "Renina-angiotensina-aldosterona")
        self.assertEqual(result.corrections[0].rule, "exact_variant")

    def test_fuzzy_high_confidence_auto_applies(self):
        result = self.normalizer.normalize("s:1", "Presenta fibrilación auriccular.")
        self.assertEqual(result.normalized_text, "Presenta fibrilación auricular.")
        self.assertEqual(result.corrections[0].rule, "glossary_fuzzy")
        self.assertGreaterEqual(result.corrections[0].confidence,
                                self.normalizer.config.auto_threshold)

    def test_additional_medical_terms_cover_exact_fuzzy_and_suggestion_paths(self):
        cases = (
            ("insuficiencia cardíaaca", "insuficiencia cardíaca", 1, 0),
            ("ecocardiografia transtoracica", "ecocardiografía transtorácica", 1, 0),
            ("hemoglobina glicosiladaa", "hemoglobina glicosilada", 1, 0),
            ("antagonistas del receptor de angiotensina dos",
             "antagonistas del receptor de angiotensina II", 1, 0),
        )
        for index, (raw, expected, correction_count, suggestion_count) in enumerate(cases):
            with self.subTest(raw=raw):
                self.normalizer.reset()
                result = self.normalizer.normalize(f"medical:{index}", raw)
                self.assertEqual(result.normalized_text, expected)
                self.assertEqual(len(result.corrections), correction_count)
                self.assertEqual(len(result.suggestions), suggestion_count)

    def test_fuzzy_below_auto_is_suggestion(self):
        result = self.normalizer.normalize("s:1", "Se documentó fibrilación aurikular.")
        self.assertEqual(result.normalized_text, result.raw_text)
        suggestion = next(item for item in result.suggestions
                          if item.candidate == "fibrilación auricular")
        self.assertLess(suggestion.confidence, self.normalizer.config.auto_threshold)
        self.assertGreaterEqual(suggestion.confidence,
                                self.normalizer.config.suggest_threshold)

    def test_below_suggestion_threshold_is_no_match(self):
        result = self.normalizer.normalize("s:1", "Se observa insuficienza kardyaka.")
        self.assertEqual(result.normalized_text, result.raw_text)
        self.assertFalse(result.corrections)
        self.assertFalse(result.suggestions)

    def test_negative_near_matches_are_unchanged(self):
        text = "La función renal, arterial y la tensión del receptor permanecen estables."
        result = self.normalizer.normalize("s:1", text)
        self.assertEqual(result.normalized_text, text)
        self.assertFalse(result.corrections)
        self.assertFalse(result.suggestions)

    def test_overlapping_spans_choose_longer_exact_term(self):
        normalizer = TerminologyNormalizer.from_documents([{"terms": [
                {"canonical": "receptor de angiotensina II",
                 "variants": ["receptor angiotensina dos"]},
                {"canonical": "angiotensina II", "variants": ["angiotensina dos"]},
            ]}])
        result = normalizer.normalize("s:1", "receptor angiotensina dos")
        self.assertEqual(result.normalized_text, "receptor de angiotensina II")
        self.assertEqual(len(result.corrections), 1)

    def test_repeated_terms_and_punctuation_are_preserved(self):
        result = self.normalizer.normalize(
            "s:1", "Systólica, systólica; y systólica.")
        self.assertEqual(result.normalized_text,
                         "Sistólica, sistólica; y sistólica.")
        self.assertEqual(len(result.corrections), 3)

    def test_context_creates_non_retroactive_cross_segment_suggestion(self):
        first = self.normalizer.normalize(
            "s:1", "incluyendo el sistema herenina angiotensina")
        second = self.normalizer.normalize("s:2", "al dosterona.")
        self.assertEqual(first.normalized_text, first.raw_text)
        self.assertEqual(second.normalized_text, "aldosterona.")
        suggestion = next(item for item in second.suggestions if item.cross_segment)
        self.assertEqual(suggestion.candidate, "renina-angiotensina-aldosterona")
        self.assertEqual(suggestion.previous_segment_id, "s:1")

    def test_reset_clears_cross_segment_context(self):
        self.normalizer.normalize("s:1", "sistema herenina angiotensina")
        self.normalizer.reset()
        result = self.normalizer.normalize("s:2", "al dosterona.")
        self.assertFalse([item for item in result.suggestions if item.cross_segment])

    def test_same_input_is_deterministic(self):
        first = TerminologyNormalizer.from_config().normalize(
            "s:1", "Fibrilación auriccular y presión systólica.")
        second = TerminologyNormalizer.from_config().normalize(
            "s:1", "Fibrilación auriccular y presión systólica.")
        self.assertEqual(first.raw_text, second.raw_text)
        self.assertEqual(first.normalized_text, second.normalized_text)
        self.assertEqual(first.corrections, second.corrections)
        self.assertEqual(first.suggestions, second.suggestions)
        self.assertEqual(first.known_terms, second.known_terms)

    def test_thresholds_require_auto_to_exceed_suggestion(self):
        with self.assertRaisesRegex(ValueError, "auto_threshold must exceed"):
            NormalizerConfig(auto_threshold=.9, suggest_threshold=.9)

    def test_thresholds_and_context_are_configurable_from_environment(self):
        values = {
            "NORMALIZER_AUTO_THRESHOLD": ".98",
            "NORMALIZER_SUGGEST_THRESHOLD": ".8",
            "NORMALIZER_MAX_TOKEN_DELTA": "2",
            "NORMALIZER_CONTEXT_WORDS": "11",
            "NORMALIZER_COLLAPSED_MIN_CHARACTERS": "12",
            "NORMALIZER_COLLAPSED_MAX_EDITS": "2",
        }
        with patch.dict(os.environ, values):
            config = NormalizerConfig.from_env()
        self.assertEqual((config.auto_threshold, config.suggest_threshold,
                          config.max_token_delta, config.context_words,
                          config.collapsed_min_characters, config.collapsed_max_edits),
                         (.98, .8, 2, 11, 12, 2))

    def test_conference_glossary_loads_without_changing_base(self):
        base = json.loads((Path(__file__).parents[1] / "glossaries/medical_base.json").read_text(
            encoding="utf-8"))
        conference = {"terms": [{
                "canonical": "CARDIO-X", "variants": ["cardio equis"],
                "auto_apply": "exact"}]}
        normalizer = TerminologyNormalizer.from_documents([base, conference])
        result = normalizer.normalize("s:1", "cardio equis y presión systólica")
        self.assertEqual(result.normalized_text, "CARDIO-X y presión sistólica")

    def test_real_medical_replay_is_conservative(self):
        fixture = json.loads((Path(__file__).parents[1]
                              / "benchmarks/medical_real_snapshots.json").read_text(
                                  encoding="utf-8"))
        manager = SegmentManager()
        normalizer = TerminologyNormalizer.from_config()
        normalized = [normalizer.normalize(segment.id, segment.text)
                      for _, result in replay(fixture["events"], manager)
                      for segment in result.ready_segments]
        corrections = [item for result in normalized for item in result.corrections]
        suggestions = [item for result in normalized for item in result.suggestions]
        self.assertEqual([(item.source, item.replacement) for item in corrections],
                         [("systólica", "sistólica"),
                          ("al dosterona", "aldosterona")])
        self.assertEqual(sum(item.cross_segment for item in suggestions), 1)
        joined = " ".join(item.normalized_text for item in normalized)
        self.assertIn("Suficio patología", joined)
        self.assertIn("pertencios", joined)

    def test_real_milestone_3_1_observation(self):
        raw = (Path(__file__).parents[1] / "benchmarks/medical_m3_1_observed.txt").read_text(
            encoding="utf-8").rstrip("\r\n")
        result = self.normalizer.normalize("live:1", raw)
        changes = {(item.source, item.replacement) for item in result.corrections}
        suggestions = {(item.source, item.candidate) for item in result.suggestions}
        self.assertEqual(changes, {
            ("systólica", "sistólica"),
            ("renina angiotensina al desterona", "renina-angiotensina-aldosterona"),
            ("accidente cerebro vascular", "accidente cerebrovascular"),
            ("angiotensina 2", "angiotensina II"),
        })
        self.assertEqual(suggestions, {
            ("suficio patología", "fisiopatología"),
            ("resistencias vascular periférica", "resistencia vascular periférica"),
            ("diabetes mellitos", "diabetes mellitus"),
            ("diuréticos diacídicos", "diuréticos tiazídicos"),
        })
        self.assertIn("del enzima convertidora de angiotensina", result.normalized_text)
        self.assertIn("y incluyendo", result.normalized_text)
        self.assertIn("de la del sistema", result.normalized_text)

    def test_cerebrovascular_split_is_a_safe_single_term_merge(self):
        result = self.normalizer.normalize("new:1", "riesgo cerebro vascular elevado")
        self.assertEqual(result.normalized_text, "riesgo cerebrovascular elevado")
        self.assertEqual(result.corrections[0].confidence, 1.)

    def test_split_single_term_requires_strong_technical_evidence(self):
        positive = {
            "al desterona": "aldosterona",
            "electro cardiograma": "electrocardiograma",
            "micro albuminuria": "microalbuminuria",
        }
        for raw, expected in positive.items():
            with self.subTest(raw=raw):
                self.normalizer.reset()
                result = self.normalizer.normalize("new:1", raw)
                self.assertEqual(result.normalized_text, expected)
                self.assertEqual(result.corrections[0].rule, "glossary_fuzzy")
                self.assertGreaterEqual(result.corrections[0].confidence,
                                        self.normalizer.config.auto_threshold)

        for raw in ("alta tensión", "arteria renal", "cardio grama",
                    "micro economía", "angiotensina"):
            with self.subTest(raw=raw):
                self.normalizer.reset()
                result = self.normalizer.normalize("negative:1", raw)
                self.assertEqual(result.normalized_text, raw)
                self.assertFalse(result.corrections)

    def test_spacing_is_normalized_without_changing_raw(self):
        raw = "  condición  cardiovascular ,sin alterar 3,5 ni EE.UU.  "
        result = self.normalizer.normalize("spacing:1", raw)
        self.assertEqual(result.raw_text, raw)
        self.assertEqual(result.normalized_text,
                         "condición cardiovascular, sin alterar 3,5 ni EE.UU.")
        spacing = [item for item in result.corrections
                   if item.rule == "deterministic_spacing"]
        self.assertGreaterEqual(len(spacing), 4)


if __name__ == "__main__":
    unittest.main()
