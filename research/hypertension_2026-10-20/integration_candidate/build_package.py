"""Derive a research package; write exclusively beside this file, never in TRAD."""
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
ROOT = RESEARCH.parents[1]
VERSION = "1.0.0-research"
INPUTS = [
    "hypertension_research_en_es.json", "bilingual_verification.json",
    "alias_inventory.json", "alias_review_decisions.json",
    "alias_corrections_proposed.json", "surface_verification_124.json",
    "surface_verification_124_corrections.json", "session3_terminology_corrections.json",
    "sources.json", "alias_source_catalog.json", "surface_verification_124_sources.json",
    "alias_definition_evidence.json",
]
OUTPUTS = [
    "concepts.json", "form_decisions.json", "normalization_en.json",
    "normalization_es.json", "translation_en_es.json", "restrictions.json",
    "collisions.json", "sources.json", "changes_applied.json", "provenance.json",
]
BUCKETS = {
    "lexical_variant_for_research": "reviewable_variant",
    "orthographic_variant": "reviewable_variant",
    "abbreviation_context_only": "definition_required",
    "collision_requires_explicit_definition": "definition_required",
    "exclude_strict_equivalence": "excluded_strict_equivalence",
    "contextual_equivalence": "context_required",
    "inflection_preserve_number": "preserve_inflection",
    "unit_symbol_preserve": "preserve_unit_symbol",
}
LATEST = {
    "literal_verified_in_concept_context", "unsafe_equivalence_reconfirmed",
    "ambiguous_reference_restricted", "no_acceptable_literal_attestation",
    "limited_evidence_not_accepted",
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write(name, data):
    # Deliberately accepts only a filename, with no user-selectable output path.
    if Path(name).name != name:
        raise ValueError("Output must remain inside integration_candidate")
    (HERE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def document(kind, **data):
    return dict(schema_version="1.0", package_version=VERSION, kind=kind,
                status="research_preparation_only", integrated=False,
                runtime_approved=False, automatic_substitution_approved=False, **data)


def comparison_key(text):
    """Analytical copy of runtime token folding; NEVER use this to rewrite text."""
    tokens = re.findall(r"[^\W_]+(?:[’'][^\W_]+)*", text, re.UNICODE)
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", token.casefold())
                            if not unicodedata.combining(c)) for token in tokens)


def unique(rows, field):
    result = {r[field]: r for r in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate {field}")
    return result


def assert_identity(a, b):
    for field in ("concept_id", "form", "language"):
        if a[field] != b[field]:
            raise ValueError(f"Overlay identity mismatch: {a['form_id']} {field}")


def resolve_form(base, latest=None, restriction=None, unsupported=None):
    """Later evidence can restrict a form, but cannot approve an automatic alias."""
    bucket = BUCKETS[base["status"]]  # Unknown statuses must fail closed.
    if latest:
        assert_identity(base, latest)
        if latest["previous_alias_safety_status"] != base["status"]:
            raise ValueError("Overlay baseline safety status changed")
        if latest["decision"] not in LATEST:
            raise ValueError(f"Unknown latest decision: {latest['decision']}")
    if restriction:
        assert_identity(base, restriction)
    if unsupported:
        assert_identity(base, unsupported)
    decision = latest["decision"] if latest else None
    if bucket == "excluded_strict_equivalence" or decision == "unsafe_equivalence_reconfirmed":
        bucket = "excluded_strict_equivalence"
    elif restriction and restriction["research_action"] == "retire_unattested_ambiguous_alias":
        bucket = "excluded_strict_equivalence"
    elif unsupported or decision in {"no_acceptable_literal_attestation", "limited_evidence_not_accepted"}:
        bucket = "held_for_evidence"
    elif decision == "ambiguous_reference_restricted":
        bucket = "context_required"
    if latest:
        attestation = latest["attestation"]
        evidence_status = ("literal_verified_in_concept_context" if decision == "literal_verified_in_concept_context"
                           else "not_accepted" if unsupported else "literal_does_not_establish_equivalence")
    else:
        attestation = base["literal_location"]
        evidence_status = "prior_literal_location_only_not_semantic_approval"
    return {
        "form_id": base["form_id"], "concept_id": base["concept_id"],
        "language": base["language"], "form": base["form"],
        "occurrence_ids": base["occurrence_ids"], "roles": base["roles"],
        "baseline_safety_status": base["status"], "bucket": bucket,
        "baseline_editorial_reason": base["editorial_reason"],
        "latest_decision": decision, "latest_editorial_note": latest["editorial_note"] if latest else None,
        "latest_research_action": latest["research_action"] if latest else None,
        "specific_restriction": copy.deepcopy(restriction),
        "unsupported_variant_restriction": copy.deepcopy(unsupported),
        "surface_evidence_status": evidence_status, "attestation": copy.deepcopy(attestation),
        "evidence_history": copy.deepcopy(base["evidence"]),
        "canonical_verification_record_id": base["concept_id"],
        "query_review_eligible": bucket == "reviewable_variant",
        "strict_equivalence_approved": False, "automatic_substitution_approved": False,
        "provenance": {"baseline": "alias_review_decisions.json#" + base["form_id"],
                       "latest": "surface_verification_124.json#" + base["form_id"] if latest else None},
    }


def derive_abbreviations(concepts, corrections):
    changes = []
    expansions = corrections["abbreviation_expansion_proposals"]
    meanings = corrections["abbreviation_other_meanings_proposals"]
    matched = Counter()
    for concept in concepts:
        for abbr in concept["abbreviations"]:
            abbr["automatic_expansion_approved"] = False
            abbr["usage_policy"] = "local_definition_and_language_required"
            for kind, proposals in [("expansion", expansions), ("other_meanings", meanings)]:
                for index, proposal in enumerate(proposals):
                    if (proposal["concept_id"], proposal["form"], proposal["language"]) != (
                            concept["id"], abbr["form"], abbr["language"]):
                        continue
                    if abbr[kind] != proposal["previous"]:
                        raise ValueError(f"Abbreviation correction baseline differs: {proposal}")
                    updated = proposal["proposed"] if kind == "expansion" else proposal["proposed_distinct_meanings"]
                    previous = copy.deepcopy(abbr[kind])
                    abbr[kind] = copy.deepcopy(updated)
                    if kind == "other_meanings":
                        abbr["unverified_historical_notes"] = copy.deepcopy(proposal["demote_to_unverified_notes"])
                    abbr.setdefault("correction_history", []).append(copy.deepcopy(proposal))
                    changes.append(dict(concept_id=concept["id"], form=abbr["form"], language=abbr["language"],
                                        field="abbreviations." + kind, previous=previous, derived=copy.deepcopy(updated),
                                        status="applied_to_derived_research_only_not_runtime_approved"))
                    matched[(kind, index)] += 1
    expected = {(kind, i) for kind, rows in [("expansion", expansions), ("other_meanings", meanings)]
                for i in range(len(rows))}
    if set(matched) != expected or any(n != 1 for n in matched.values()):
        raise ValueError("Every abbreviation proposal must resolve exactly once")
    return changes


def collision_groups(members, language_aware):
    groups = defaultdict(list)
    for member in members:
        k = comparison_key(member["form"])
        if not k:
            raise ValueError("Empty comparison key")
        groups[(member["language"] if language_aware else "mixed", k)].append(member)
    result = []
    for (lang, key), group in sorted(groups.items()):
        ids = sorted({m["concept_id"] for m in group})
        if len(ids) > 1:
            result.append(dict(language=lang, comparison_key=key, concept_ids=ids, members=group,
                               decision="no_precedence_selection_require_concept_context"))
    return result


def build():
    baseline = load(HERE / "protected_files.json")
    protected = {r["path"]: r for r in baseline["files"]}
    inputs = {}
    for name in INPUTS:
        path = RESEARCH / name
        relative = path.relative_to(ROOT).as_posix()
        if sha(path) != protected[relative]["sha256"]:
            raise ValueError(f"Protected research input changed: {name}")
        inputs[name] = load(path)
    data, bilingual = inputs[INPUTS[0]], inputs[INPUTS[1]]
    audit, old, latest, overlay = (inputs["alias_review_decisions.json"], inputs["alias_corrections_proposed.json"],
                                  inputs["surface_verification_124.json"], inputs["surface_verification_124_corrections.json"])
    checks = [
        (audit["input_dataset_sha256"], INPUTS[0]),
        (audit["input_inventory_sha256"], "alias_inventory.json"),
        (old["input_dataset_sha256"], INPUTS[0]),
        (latest["baseline_alias_review_sha256"], "alias_review_decisions.json"),
        (overlay["input_alias_audit_sha256"], "alias_review_decisions.json"),
    ]
    for digest, name in checks:
        if digest != sha(RESEARCH / name):
            raise ValueError(f"Evidence chain mismatch: {name}")
    c_by_id, v_by_id = unique(data["concepts"], "id"), unique(bilingual["records"], "id")
    reviews = unique(audit["form_reviews"], "form_id")
    latest_by_id = unique(latest["records"], "form_id")
    restricted = unique(overlay["semantic_restrictions"], "form_id")
    unsupported = unique(overlay["forms_without_accepted_literal_attestation"], "form_id")
    if len(c_by_id) != 657 or set(c_by_id) != set(v_by_id) or len(reviews) != 567 or len(latest_by_id) != 124:
        raise ValueError("Unexpected canonical/alias coverage")
    if not (set(restricted) <= set(latest_by_id) <= set(reviews)) or not set(unsupported) <= set(latest_by_id):
        raise ValueError("Overlay has dangling IDs")
    forms = [resolve_form(r, latest_by_id.get(fid), restricted.get(fid), unsupported.get(fid))
             for fid, r in reviews.items()]
    by_concept = defaultdict(list)
    for form in forms:
        if form["concept_id"] not in c_by_id:
            raise ValueError("Unknown concept")
        by_concept[form["concept_id"]].append(form["form_id"])
    concepts = []
    reference_ids = {r["concept_id"] for r in audit["reference_identity_guards"]}
    for cid, c in c_by_id.items():
        v = v_by_id[cid]
        if (c["canonical_en"], c["preferred_es"]) != (v["canonical_en"], v["preferred_es"]):
            raise ValueError("Canonical pair differs from verification ledger")
        concepts.append(dict(id=cid, canonical_en=c["canonical_en"], preferred_es=c["preferred_es"],
                             category=c["category"], scope=c["scope"], origin=c["origin"],
                             clinical_context=c["clinical_context"], notes=c["notes"],
                             source_ids=c["source_ids"], evidence=copy.deepcopy(c["evidence"]),
                             bilingual_verification=copy.deepcopy(v), form_ids=by_concept[cid],
                             abbreviations=copy.deepcopy(c["abbreviations"]),
                             reference_context_required=cid in reference_ids,
                             reference_identity_guard=[g for g in audit["reference_identity_guards"] if g["concept_id"] == cid],
                             clinical_distinction_guards=[g for g in audit["clinical_distinction_guards"]
                                                         if cid in {g["a_concept_id"], g["b_concept_id"]}],
                             canonical_revision_history=[g for g in inputs["session3_terminology_corrections.json"]["corrections"]
                                                         if g["id"] == cid],
                             automatic_substitution_approved=False))
    changes = derive_abbreviations(concepts, old)
    for row in old["exclude_from_strict_alias_sets"]:
        assert_identity(reviews[row["form_id"]], row)
        if next(f for f in forms if f["form_id"] == row["form_id"])["bucket"] != "excluded_strict_equivalence":
            raise ValueError("An older strict exclusion was lost")
    for row in old["retain_only_with_conditions"]:
        f = next(f for f in forms if f["form_id"] == row["form_id"])
        assert_identity(f, row)
        f["prior_context_condition"] = row["condition"]
    members = [dict(concept_id=c["id"], language=lang, form=c[field], role="canonical", form_id=None)
               for c in concepts for lang, field in [("en", "canonical_en"), ("es", "preferred_es")]]
    members += [dict(concept_id=f["concept_id"], language=f["language"], form=f["form"], role="alternative",
                     form_id=f["form_id"]) for f in forms]
    mixed, per_language = collision_groups(members, False), collision_groups(members, True)
    mixed_ids = {fid for g in mixed for fid in [m["form_id"] for m in g["members"]] if fid}
    for form in forms:
        if form["form_id"] in mixed_ids:
            form["query_review_eligible"] = False
            form["collision_restriction"] = "explicit_local_definition_required"
    # Compare against existing files without importing or executing application code.
    canonical_index = defaultdict(set)
    for c in data["concepts"]:
        for language, label in [("en", c["canonical_en"]), ("es", c["preferred_es"])]:
            canonical_index[(language, comparison_key(label))].add(c["id"])
        for original in c["original_entries"]:
            canonical_index[("en", comparison_key(original["canonical"]))].add(c["id"])
    # A reviewed lexical variant may identify a legacy research concept for this
    # comparison, without becoming a strict synonym or a text replacement rule.
    canonical_and_original_keys = set(canonical_index)
    for f in forms:
        if f["query_review_eligible"]:
            canonical_index[(f["language"], comparison_key(f["form"]))].add(f["concept_id"])
    external_checks = []
    for name, language in [("medical_base_en.json", "en"), ("medical_base.json", "es"), ("conference.json", None)]:
        path = ROOT / "glossaries" / name
        rel = path.relative_to(ROOT).as_posix()
        if sha(path) != protected[rel]["sha256"]:
            raise ValueError("Existing glossary changed")
        for term in load(path)["terms"]:
            candidates = canonical_index.get((language, comparison_key(term["canonical"])), set())
            for role, values in [("canonical", [term["canonical"]]), ("aliases", term.get("aliases", [])),
                                 ("variants", term.get("variants", []))]:
                for label in values:
                    matches = [m for m in members if comparison_key(m["form"]) == comparison_key(label)
                               and (language is None or m["language"] == language)]
                    if matches:
                        ids = sorted({m["concept_id"] for m in matches})
                        relation = ("same_concept_overlap" if len(candidates) == 1 and set(ids) == candidates else
                                    "unresolved_existing_target" if not candidates else "conflicting_concept_targets")
                        external_checks.append(dict(file=rel, language=language, existing_canonical=term["canonical"],
                                                    existing_role=role, existing_form=label,
                                                    existing_target_ids=sorted(candidates), package_concept_ids=ids,
                                                    existing_target_resolution_basis=("canonical_or_original_entry" if
                                                        (language, comparison_key(term["canonical"])) in canonical_and_original_keys
                                                        else "review_variant_for_research_screening_only" if candidates else "unresolved"),
                                                    package_form_ids=sorted({m["form_id"] for m in matches if m["form_id"]}),
                                                    relation=relation, decision="observe_only_never_merge_by_file_order"))
    conflict_forms = {fid for r in external_checks if r["relation"] != "same_concept_overlap" for fid in r["package_form_ids"]}
    for f in forms:
        if f["form_id"] in conflict_forms:
            f["query_review_eligible"] = False
            f["existing_glossary_restriction"] = "target_reconciliation_required"
    sources = copy.deepcopy(inputs["sources.json"] + inputs["alias_source_catalog.json"]["sources"]
                            + inputs["surface_verification_124_sources.json"]["sources"])
    source_index = unique(sources, "id")
    for c in concepts:
        for sid in c["source_ids"] + [c["bilingual_verification"][lang + "_attestation"]["source_id"] for lang in ("en", "es")]:
            if sid not in source_index:
                raise ValueError(f"Unknown source {sid}")
    payloads = {}
    payloads["concepts.json"] = document("consolidated_concepts", concepts=concepts)
    payloads["form_decisions.json"] = document("effective_alternative_decisions", forms=forms,
                                             bucket_counts=dict(sorted(Counter(f["bucket"] for f in forms).items())))
    for language, field in [("en", "canonical_en"), ("es", "preferred_es")]:
        entries = []
        for c in concepts:
            alternatives = [f["form_id"] for f in forms if f["concept_id"] == c["id"] and f["language"] == language
                            and f["query_review_eligible"]]
            entries.append(dict(concept_id=c["id"], canonical=c[field], policy="observe_only_no_text_rewrite",
                                review_alternative_ids=alternatives,
                                restricted_alternative_ids=[f["form_id"] for f in forms if f["concept_id"] == c["id"]
                                                            and f["language"] == language and not f["query_review_eligible"]],
                                reference_context_required=c["reference_context_required"],
                                automatic_substitution_approved=False))
        payloads[f"normalization_{language}.json"] = document("language_normalization_research_view", language=language,
                                                             policy="offline_observation_only_not_runtime_glossary", entries=entries)
    payloads["translation_en_es.json"] = document("bilingual_terminology_research_view",
        policy="concept_pairs_for_contextual_evaluation_not_global_replacement_or_provider_glossary",
        direction_activation_approved=False, entries=[dict(concept_id=c["id"], canonical_en=c["canonical_en"],
            preferred_es=c["preferred_es"], verification_method=c["bilingual_verification"]["method"],
            en_attestation=c["bilingual_verification"]["en_attestation"], es_attestation=c["bilingual_verification"]["es_attestation"],
            editorial_note=c["bilingual_verification"]["editorial_note"], clinical_context=c["clinical_context"],
            reference_context_required=c["reference_context_required"], alias_expansion_approved=False,
            automatic_substitution_approved=False) for c in concepts])
    payloads["restrictions.json"] = document("inherited_and_latest_guards", do_not_merge=data["do_not_merge"],
        rejected_equivalences=data["rejected_equivalences"], clinical_distinction_guards=audit["clinical_distinction_guards"],
        near_form_decisions=audit["near_form_decisions"], reference_identity_guards=audit["reference_identity_guards"],
        reference_identity_collision_cases=audit["reference_identity_collision_cases"],
        external_homographs=audit["external_homographs"], historical_warnings_not_reverified=audit["historical_warnings_not_reverified"],
        historical_cross_language_abbreviation_ambiguities_unverified=data["cross_language_abbreviation_ambiguities"],
        abbreviation_ambiguities_policy="Use corrected per-concept abbreviation metadata; unverified warnings remain labeled.",
        semantic_restrictions=overlay["semantic_restrictions"], forms_without_accepted_literal_attestation=overlay["forms_without_accepted_literal_attestation"],
        definition_evidence=inputs["alias_definition_evidence.json"]["records"],
        global_rules=["No automatic abbreviation expansion, fuzzy merging, number/unit/dose conversion or negation changes.",
                      "Preserve grammatical number, clinical qualifiers, trial arms, reference topic, year and protocol.",
                      "A literal location is not unconditional synonym approval; absence of evidence is not proof of non-use.",
                      "Canonical crosschecks do not certify every alias; independent clinical review and audio validation were not performed."])
    payloads["collisions.json"] = document("analytical_collision_screen", comparison="Casefold + NFKD accent removal + runtime word tokens; screening only, not runtime execution.",
        all_forms_cross_language=mixed, all_forms_per_language=per_language,
        earlier_audited_groups=audit["internal_collisions"], existing_glossary_overlaps=external_checks,
        existing_glossary_relation_counts=dict(Counter(r["relation"] for r in external_checks)),
        strict_alias_map_entries=0, automatic_rewrite_rules=0)
    payloads["sources.json"] = document("source_catalog_union_no_new_research", sources=sources,
        policy="S, AS and SF IDs and access limitations preserved. Relative evidence cache paths resolve from the parent research directory.")
    payloads["changes_applied.json"] = document("derived_changes_only", abbreviation_changes=changes,
        strict_exclusion_form_ids=[f["form_id"] for f in forms if f["bucket"] == "excluded_strict_equivalence"],
        evidence_hold_form_ids=[f["form_id"] for f in forms if f["bucket"] == "held_for_evidence"],
        latest_overlay_applied_to=list(latest_by_id), canonical_pairs_renamed=0,
        canonical_revision_history_preserved=inputs["session3_terminology_corrections.json"]["corrections"],
        original_policies_imported=False)
    paths = [RESEARCH / n for n in INPUTS] + [ROOT / "glossaries" / n for n in ["medical_base_en.json", "medical_base.json", "conference.json"]]
    paths += [ROOT / "app/captions/terminology_normalizer.py"]
    payloads["provenance.json"] = document("inputs_and_precedence", baseline_recorded_at_utc=baseline["recorded_at_utc"],
        inputs=[protected[p.relative_to(ROOT).as_posix()] for p in paths],
        precedence=["Canonical pairs: dataset agrees with bilingual_verification.json; retain stable IDs and exact labels.",
                    "Alias inventory + alias_review_decisions.json + alias_corrections_proposed.json.",
                    "surface_verification_124.json and its corrections override older evidence/eligibility only; retain prior restrictions.",
                    "All resulting views remain observation-only; no operational approval is inferred."],
        not_used_as_release_source="medical_base_en_extended_candidate.json: frozen earlier 640-entry candidate",
        write_boundary="Only this integration_candidate directory; no application import, configuration, network or live session.")
    for name, payload in payloads.items():
        write(name, payload)
    return payloads


def verify_protected():
    baseline = load(HERE / "protected_files.json")
    observations = []
    strict_count = 0
    for row in baseline["files"]:
        path = ROOT / row["path"]
        strict = row["path"].startswith(("research/", "glossaries/"))
        strict_count += int(strict)
        observed = sha(path) if path.is_file() else None
        if observed != row["sha256"]:
            if strict:
                raise ValueError(f"Existing protected research/glossary changed: {row['path']}")
            observations.append(dict(path=row["path"], baseline_sha256=row["sha256"], observed_sha256=observed,
                                     status="observed_change_outside_builder_write_boundary_not_reverted"))
    expected = {r["path"] for r in baseline["files"]}
    added = []
    for folder in ["research", "glossaries", "app", "trad_lab", "tests"]:
        for path in (ROOT / folder).rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts or HERE in path.parents:
                continue
            if path.relative_to(ROOT).as_posix() not in expected:
                added.append(path.relative_to(ROOT).as_posix())
    strict_additions = [p for p in added if p.startswith(("research/", "glossaries/"))]
    if strict_additions:
        raise ValueError(f"Unexpected additions to existing research/glossaries: {strict_additions}")
    return dict(existing_files_checked=len(expected),
                research_and_glossary_files_checked=strict_count,
                all_existing_research_and_glossaries_byte_identical=True,
                all_existing_files_byte_identical=not observations,
                unchanged_existing_files=len(expected) - len(observations),
                changes_observed_outside_write_boundary=observations,
                additions_observed_outside_write_boundary=added,
                builder_write_boundary="integration_candidate only; observations are not reverted or attributed to an actor",
                production_connected=False, runtime_or_audio_tests_run=False)


def seal():
    names = OUTPUTS + ["protected_files.json", "build_package.py", "test_package.py", "README.txt", "validation.json"]
    write("manifest.json", document("package_integrity_manifest", files=[dict(name=n, bytes=(HERE/n).stat().st_size,
                  sha256=sha(HERE/n)) for n in names], self_hash_excluded=True))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    payloads = build()
    checked = subprocess.run([sys.executable, "-B", str(HERE / "test_package.py")], capture_output=True, text=True,
                             encoding="utf-8", cwd=HERE)
    if checked.returncode:
        raise SystemExit(checked.stdout + checked.stderr)
    protection = verify_protected()
    write("validation.json", document("package_structural_checks_not_clinical_or_audio_validation", passed=True,
        test_output=checked.stdout + checked.stderr, protection=protection,
        concepts=len(payloads["concepts.json"]["concepts"]), alternative_forms=len(payloads["form_decisions.json"]["forms"]),
        bucket_counts=payloads["form_decisions.json"]["bucket_counts"],
        latest_decisions_applied=len(payloads["changes_applied.json"]["latest_overlay_applied_to"]),
        abbreviation_changes=len(payloads["changes_applied.json"]["abbreviation_changes"]),
        query_review_variants=sum(f["query_review_eligible"] for f in payloads["form_decisions.json"]["forms"]),
        internal_cross_language_collision_groups=len(payloads["collisions.json"]["all_forms_cross_language"]),
        internal_same_language_collision_groups=len(payloads["collisions.json"]["all_forms_per_language"]),
        existing_glossary_relations=payloads["collisions.json"]["existing_glossary_relation_counts"],
        automatic_substitutions_approved=0, independent_clinician_review="not_performed"))
    seal()
    print(json.dumps(load(HERE / "validation.json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
