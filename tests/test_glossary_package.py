"""Offline tests only; no service, decoder, network or provider is constructed."""
import copy
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.captions.terminology_normalizer import TerminologyNormalizer, NormalizerConfig
from trad_lab.glossary_package import (
    PACKAGE, RESULTS, ResearchPackage, ExactObservationNormalizer, strict_observe,
    full_span_target, load, digest,
)


class PackageLaboratoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = ResearchPackage(PACKAGE)

    def test_frozen_package_manifest_657_pairs_and_265_selected_variants(self):
        self.assertEqual(657, len(self.package.concepts))
        self.assertEqual(567, len(self.package.forms))
        self.assertEqual(265, sum(f["query_review_eligible"] for f in self.package.forms.values()))
        self.assertEqual(657, len(self.package.document("en")["terms"]))
        self.assertEqual(657, len(self.package.document("es")["terms"]))

    def test_manifest_tamper_rejected_without_writing_evidence(self):
        # Only an in-memory hash result is changed; the source package is untouched.
        original = digest
        def tampered(path):
            return "bad-digest" if Path(path).name == "concepts.json" else original(path)
        with patch("trad_lab.glossary_package.digest", side_effect=tampered):
            with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                ResearchPackage(PACKAGE)

    def test_only_suggest_policies_and_explicit_language(self):
        for lang in ("en", "es"):
            self.assertTrue(all(t["auto_apply"] == "suggest" for t in self.package.document(lang)["terms"]))
            self.package.observer(lang)
        with self.assertRaises(ValueError):
            self.package.document("auto")

    def test_quarantined_forms_never_added_to_lab_aliases(self):
        for lang in ("en", "es"):
            terms = self.package.document(lang)["terms"]
            by_name = {t["canonical"]: t for t in terms}
            for f in self.package.forms.values():
                if f["language"] != lang or f["query_review_eligible"]:
                    continue
                c = self.package.concepts[f["concept_id"]]
                canonical = c["canonical_en" if lang == "en" else "preferred_es"]
                self.assertNotIn(f["form"], by_name[canonical]["aliases"])

    def test_actual_loader_blocks_injected_mra_collision_even_in_suggest(self):
        doc = {"terms": [{"canonical": "magnetic resonance angiography", "aliases": ["MRA"], "auto_apply": "suggest"},
                         {"canonical": "mineralocorticoid receptor antagonist", "aliases": ["MRA"], "auto_apply": "suggest"}]}
        with self.assertRaisesRegex(ValueError, "Ambiguous glossary form"):
            ExactObservationNormalizer.from_documents([doc], NormalizerConfig())

    def test_research_view_cannot_be_loaded_as_runtime_glossary(self):
        with self.assertRaisesRegex(ValueError, "terms array"):
            TerminologyNormalizer.from_documents([self.package.views["en"]], NormalizerConfig())

    def test_strict_output_rejects_even_native_spacing_changes(self):
        text = "  No edema,please;keep 5 mg and <10%.  "
        obs = ExactObservationNormalizer.from_documents([{"terms": []}], NormalizerConfig())
        result = strict_observe(obs, "s", text)
        self.assertEqual(text, result["controlled_text"])
        self.assertNotEqual(text, result["native_candidate_text"])
        self.assertTrue(result["native_corrections"])

    def test_strict_output_blocks_a_deliberately_unsafe_native_replacement(self):
        # Defense in depth: even a future accidental exact policy cannot alter
        # controlled text in this laboratory comparison.
        doc = {"terms": [{"canonical": "positive", "aliases": ["negative"], "auto_apply": "exact"}]}
        obs = ExactObservationNormalizer.from_documents([doc], NormalizerConfig())
        result = strict_observe(obs, "s", "negative")
        self.assertEqual("positive", result["native_candidate_text"])
        self.assertEqual("negative", result["controlled_text"])

    def test_fuzzy_is_off_only_for_the_named_exact_observation_profile(self):
        doc = {"terms": [{"canonical": "hypertension", "auto_apply": "suggest"}]}
        exact = ExactObservationNormalizer.from_documents([doc], NormalizerConfig())
        default = TerminologyNormalizer.from_documents([doc], NormalizerConfig())
        self.assertEqual((), exact.normalize("a", "hyper tenson").suggestions)
        self.assertTrue(default.normalize("a", "hyper tenson").suggestions)

    def test_context_reset_prevents_cross_sample_leakage(self):
        doc = {"terms": [{"canonical": "blood pressure", "aliases": ["blood preasure"], "auto_apply": "suggest"}]}
        obs = ExactObservationNormalizer.from_documents([doc], NormalizerConfig())
        obs.normalize("left", "blood")
        self.assertTrue(any(s.cross_segment for s in obs.normalize("right", "preasure").suggestions))
        obs.reset()
        self.assertFalse(any(s.cross_segment for s in obs.normalize("new-sample", "preasure").suggestions))

    def test_native_span_rules_preserve_punctuation_limitation(self):
        doc = {"terms": [{"canonical": "urine albumin/creatinine", "auto_apply": "suggest"}]}
        obs = ExactObservationNormalizer.from_documents([doc], NormalizerConfig())
        # Loader compatibility and folded tokens alone cannot prove exact coverage.
        self.assertFalse(obs.normalize("slash", "urine albumin/creatinine").suggestions)

    def test_real_numerical_signatures_and_negations_preserved(self):
        obs = self.package.observer("es")
        text = "No modificar −5%, ≥140/90 mmHg, 0,5 mg ni 5 μg/dL."
        result = strict_observe(obs, "numeric", text)
        self.assertEqual(text, result["controlled_text"])
        self.assertTrue(all(c["rule"] == "deterministic_spacing" for c in result["native_corrections"]))

    def test_translation_pairs_unique_both_directions_without_calling_provider(self):
        rows = self.package.translations
        self.assertEqual(657, len({r["canonical_en"] for r in rows}))
        self.assertEqual(657, len({r["preferred_es"] for r in rows}))
        expected = {c["id"]: (c["canonical_en"], c["preferred_es"]) for c in self.package.concepts.values()}
        self.assertEqual(expected, {r["concept_id"]: (r["canonical_en"], r["preferred_es"]) for r in rows})

    def test_documents_default_fuzzy_negation_hazard_without_applying_it(self):
        result = strict_observe(self.package.observer("en", fuzzy=True), "negation", "No edema")
        self.assertTrue(any(s.candidate == "angioedema" and s.source == "No edema" for s in result["suggestions"]))
        self.assertEqual("No edema", result["controlled_text"])
        exact = strict_observe(self.package.observer("en"), "negation", "No edema")
        self.assertFalse(any(s.candidate == "angioedema" for s in exact["suggestions"]))

    def test_documents_fuzzy_resurrection_of_excluded_alias(self):
        text = "La carga de medicación se preparó en farmacia."
        doc = self.package.document("es")
        self.assertNotIn("carga de medicación", [a for term in doc["terms"] for a in term["aliases"]])
        result = strict_observe(self.package.observer("es", fuzzy=True), "excluded", text)
        self.assertTrue(any(s.candidate == "carga de comprimidos" for s in result["suggestions"]))
        self.assertEqual(text, result["controlled_text"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
