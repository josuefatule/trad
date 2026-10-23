"""Read-only package checks, including negative cases; no application imports."""
import copy
import sys
import unittest
from collections import Counter

sys.dont_write_bytecode = True
import build_package as builder


class PackageChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = {name: builder.load(builder.HERE / name) for name in builder.OUTPUTS}
        cls.concepts = cls.package["concepts.json"]["concepts"]
        cls.forms = cls.package["form_decisions.json"]["forms"]
        cls.form_index = {f["form_id"]: f for f in cls.forms}
        cls.audit = builder.load(builder.RESEARCH / "alias_review_decisions.json")
        cls.baseline = {f["form_id"]: f for f in cls.audit["form_reviews"]}
        cls.latest = builder.load(builder.RESEARCH / "surface_verification_124.json")["records"]
        cls.overlay = builder.load(builder.RESEARCH / "surface_verification_124_corrections.json")

    def test_all_657_canonical_pairs_exactly_preserved(self):
        original = builder.load(builder.RESEARCH / "bilingual_verification.json")["records"]
        self.assertEqual(657, len(self.concepts))
        self.assertEqual({c["id"]: (c["canonical_en"], c["preferred_es"]) for c in original},
                         {c["id"]: (c["canonical_en"], c["preferred_es"]) for c in self.concepts})
        self.assertEqual({r["id"]: r for r in original},
                         {c["id"]: c["bilingual_verification"] for c in self.concepts})

    def test_all_567_forms_and_900_occurrences_once(self):
        self.assertEqual(567, len(self.form_index))
        inventory = builder.load(builder.RESEARCH / "alias_inventory.json")["occurrences"]
        actual = Counter(oid for f in self.forms for oid in f["occurrence_ids"])
        self.assertEqual(Counter(r["occurrence_id"] for r in inventory), actual)
        self.assertEqual(900, len(actual))
        for f in self.forms:
            base = self.baseline[f["form_id"]]
            self.assertEqual((base["concept_id"], base["language"], base["form"]),
                             (f["concept_id"], f["language"], f["form"]))

    def test_latest_124_records_override_evidence_without_losing_history(self):
        self.assertEqual(124, len(self.latest))
        for latest in self.latest:
            f = self.form_index[latest["form_id"]]
            self.assertEqual(latest["decision"], f["latest_decision"])
            self.assertEqual(latest["attestation"], f["attestation"])
            self.assertEqual(self.baseline[f["form_id"]]["evidence"], f["evidence_history"])
            self.assertEqual(self.baseline[f["form_id"]]["editorial_reason"], f["baseline_editorial_reason"])

    def test_13_unsupported_forms_not_in_review_selection(self):
        rows = self.overlay["forms_without_accepted_literal_attestation"]
        self.assertEqual(13, len(rows))
        for row in rows:
            f = self.form_index[row["form_id"]]
            self.assertFalse(f["query_review_eligible"])
            self.assertIn(f["bucket"], {"held_for_evidence", "excluded_strict_equivalence"})
            self.assertIsNotNone(f["unsupported_variant_restriction"])

    def test_12_strict_exclusions_include_all_old_11(self):
        rows = builder.load(builder.RESEARCH / "alias_corrections_proposed.json")["exclude_from_strict_alias_sets"]
        blocked = {f["form_id"] for f in self.forms if f["bucket"] == "excluded_strict_equivalence"}
        self.assertEqual({r["form_id"] for r in rows} | {"UF0015"}, blocked)

    def test_specific_latest_semantic_restrictions(self):
        for fid in ["UF0015", "UF0117", "UF0336", "UF0471"]:
            self.assertEqual("excluded_strict_equivalence", self.form_index[fid]["bucket"])
        for fid in ["UF0424", "UF0557"]:
            self.assertEqual("context_required", self.form_index[fid]["bucket"])
            self.assertFalse(self.form_index[fid]["query_review_eligible"])
            self.assertIsNotNone(self.form_index[fid]["specific_restriction"])

    def test_106_literal_acceptances_do_not_override_safety(self):
        accepted = [r for r in self.latest if r["decision"] == "literal_verified_in_concept_context"]
        self.assertEqual(106, len(accepted))
        for row in accepted:
            f = self.form_index[row["form_id"]]
            self.assertEqual(builder.BUCKETS[self.baseline[row["form_id"]]["status"]], f["bucket"])
            self.assertFalse(f["strict_equivalence_approved"])
            self.assertFalse(f["automatic_substitution_approved"])

    def test_abbreviation_changes_exactly_6_plus_22(self):
        changes = self.package["changes_applied.json"]["abbreviation_changes"]
        self.assertEqual(Counter({"abbreviations.expansion": 6, "abbreviations.other_meanings": 22}),
                         Counter(r["field"] for r in changes))
        for change in changes:
            c = next(c for c in self.concepts if c["id"] == change["concept_id"])
            a = next(a for a in c["abbreviations"] if (a["form"], a["language"]) == (change["form"], change["language"]))
            field = change["field"].split(".")[-1]
            self.assertEqual(change["derived"], a[field])
            self.assertFalse(a["automatic_expansion_approved"])
        self.assertEqual(176, sum(len(c["abbreviations"]) for c in self.concepts))

    def test_old_47_context_conditions_preserved(self):
        rows = builder.load(builder.RESEARCH / "alias_corrections_proposed.json")["retain_only_with_conditions"]
        self.assertEqual(47, len(rows))
        for row in rows:
            f = self.form_index[row["form_id"]]
            self.assertEqual(row["condition"], f["prior_context_condition"])
            self.assertFalse(f["query_review_eligible"])

    def test_each_language_view_covers_657_and_has_only_review_variants(self):
        for language, label in [("en", "canonical_en"), ("es", "preferred_es")]:
            view = self.package[f"normalization_{language}.json"]
            self.assertNotIn("terms", view)
            self.assertEqual(657, len(view["entries"]))
            self.assertEqual({c["id"]: c[label] for c in self.concepts},
                             {r["concept_id"]: r["canonical"] for r in view["entries"]})
            covered = []
            for entry in view["entries"]:
                self.assertEqual("observe_only_no_text_rewrite", entry["policy"])
                for fid in entry["review_alternative_ids"]:
                    f = self.form_index[fid]
                    self.assertTrue(f["query_review_eligible"])
                    self.assertEqual("reviewable_variant", f["bucket"])
                    self.assertEqual((entry["concept_id"], language), (f["concept_id"], f["language"]))
                covered += entry["review_alternative_ids"] + entry["restricted_alternative_ids"]
            self.assertEqual(Counter(f["form_id"] for f in self.forms if f["language"] == language), Counter(covered))

    def test_selected_review_forms_have_no_multi_concept_collision(self):
        # Check the actual union of canonical names and selected alternatives.
        members = [dict(concept_id=c["id"], language=lang, form=c[field])
                   for c in self.concepts for lang, field in [("en", "canonical_en"), ("es", "preferred_es")]]
        members += [dict(concept_id=f["concept_id"], language=f["language"], form=f["form"])
                    for f in self.forms if f["query_review_eligible"]]
        self.assertEqual([], builder.collision_groups(members, True))
        self.assertEqual([], builder.collision_groups(members, False))

    def test_pad_eca_mra_retained_as_restricted_collisions(self):
        groups = self.package["collisions.json"]["all_forms_cross_language"]
        keys = {r["comparison_key"] for r in groups}
        self.assertTrue({"pad", "eca", "mra"} <= keys)
        for group in groups:
            for member in group["members"]:
                if member["form_id"]:
                    self.assertFalse(self.form_index[member["form_id"]]["query_review_eligible"])

    def test_existing_glossary_conflicts_not_selected(self):
        rows = self.package["collisions.json"]["existing_glossary_overlaps"]
        self.assertTrue(rows)
        for row in rows:
            if row["relation"] != "same_concept_overlap":
                for fid in row["package_form_ids"]:
                    self.assertFalse(self.form_index[fid]["query_review_eligible"])

    def test_clinical_and_reference_guards_preserved(self):
        restrictions = self.package["restrictions.json"]
        for key in ["near_form_decisions", "clinical_distinction_guards", "reference_identity_guards", "external_homographs"]:
            self.assertEqual(self.audit[key], restrictions[key])
        self.assertEqual(60, len(restrictions["near_form_decisions"]))
        self.assertEqual(51, len(restrictions["clinical_distinction_guards"]))
        self.assertEqual(47, sum(c["reference_context_required"] for c in self.concepts))

    def test_bilingual_view_has_no_aliases_or_direction_activation(self):
        view = self.package["translation_en_es.json"]
        self.assertFalse(view["direction_activation_approved"])
        self.assertEqual(657, len(view["entries"]))
        for c, entry in zip(self.concepts, view["entries"]):
            self.assertEqual((c["id"], c["canonical_en"], c["preferred_es"]),
                             (entry["concept_id"], entry["canonical_en"], entry["preferred_es"]))
            self.assertFalse(entry["alias_expansion_approved"])
            self.assertNotIn("aliases", entry)

    def test_no_operational_policies_or_approvals_anywhere_in_payload(self):
        def walk(value):
            if isinstance(value, dict):
                self.assertNotIn("auto_apply", value)
                for key in ["automatic_substitution_approved", "automatic_expansion_approved", "runtime_approved", "integrated"]:
                    if key in value:
                        self.assertIs(False, value[key])
                for v in value.values():
                    walk(v)
            elif isinstance(value, list):
                for v in value:
                    walk(v)
        walk(self.package)

    def test_all_referenced_source_and_definition_ids_resolve(self):
        sources = self.package["sources.json"]["sources"]
        source_ids = {r["id"] for r in sources}
        self.assertEqual(324, len(sources))
        self.assertEqual(len(sources), len(source_ids))
        definitions = {r["evidence_id"] for r in self.package["restrictions.json"]["definition_evidence"]}
        def walk(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "source_id" and item is not None:
                        self.assertIn(item, source_ids)
                    if key in {"source_ids", "translation_crosscheck_source_ids"}:
                        self.assertTrue(set(item) <= source_ids)
                    if key == "definition_evidence_ids":
                        self.assertTrue(set(item) <= definitions)
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(self.package)

    def test_negative_unknown_status_fails_closed(self):
        row = copy.deepcopy(self.baseline["UF0002"])
        row["status"] = "new_unreviewed_status"
        with self.assertRaises(KeyError):
            builder.resolve_form(row)

    def test_negative_overlay_wrong_concept_rejected(self):
        latest = copy.deepcopy(self.latest[0])
        latest["concept_id"] = "wrong"
        with self.assertRaises(ValueError):
            builder.resolve_form(self.baseline[latest["form_id"]], latest)

    def test_negative_overlay_wrong_baseline_or_unknown_decision_rejected(self):
        latest = copy.deepcopy(self.latest[0])
        latest["previous_alias_safety_status"] = "orthographic_variant"
        with self.assertRaises(ValueError):
            builder.resolve_form(self.baseline[latest["form_id"]], latest)
        latest["previous_alias_safety_status"] = self.baseline[latest["form_id"]]["status"]
        latest["decision"] = "automatically_approved"
        with self.assertRaises(ValueError):
            builder.resolve_form(self.baseline[latest["form_id"]], latest)

    def test_negative_literal_hit_cannot_promote_excluded_alias(self):
        row = copy.deepcopy(self.baseline["UF0117"])
        latest = copy.deepcopy(next(r for r in self.latest if r["form_id"] == "UF0117"))
        latest["decision"] = "literal_verified_in_concept_context"
        resolved = builder.resolve_form(row, latest)
        self.assertEqual("excluded_strict_equivalence", resolved["bucket"])
        self.assertFalse(resolved["query_review_eligible"])

    def test_negative_case_accent_and_hyphen_collision_detected(self):
        members = [dict(concept_id="A", language="es", form="Tensión-arterial"),
                   dict(concept_id="B", language="es", form="tension arterial")]
        self.assertEqual(1, len(builder.collision_groups(members, True)))
        self.assertEqual("tension arterial", builder.comparison_key(members[0]["form"]))

    def test_units_and_inflections_remain_exact_surface_strings(self):
        for f in self.forms:
            if f["baseline_safety_status"] in {"unit_symbol_preserve", "inflection_preserve_number"}:
                self.assertEqual(self.baseline[f["form_id"]]["form"], f["form"])
                self.assertFalse(f["query_review_eligible"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
