"""CPU-only validation of a frozen research package. No LIVE or provider imports.

Only main() writes, and only inside a new, explicitly prepared results directory.
The laboratory adapter is never imported by app/ or selected through LIVE config.
"""
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

from app.captions.identity_normalizer import IdentityNormalizer
from app.captions.terminology_normalizer import NormalizerConfig, TerminologyNormalizer, _tokens
from trad_lab.glossary import shadow
from trad_lab.metrics import metrics, measurement_signatures, term_inventory, tokens

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "research/hypertension_2026-10-20/integration_candidate"
RESULTS = PACKAGE.parent / "laboratory_validation_v1"
CACHED = ROOT / "logs/trad_lab/20261020T074247Z/evaluation"
MODELS = ("small", "medium", "large-v3-turbo")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save(out, name, value):
    if Path(name).name != name:
        raise ValueError("Results filename must have no directory components")
    (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def unique(rows, key):
    index = {r[key]: r for r in rows}
    if len(index) != len(rows):
        raise ValueError(f"Duplicate {key}")
    return index


class ExactObservationNormalizer(TerminologyNormalizer):
    """LAB profile: real exact matcher and context, with unapproved fuzzy OFF."""
    def _fuzzy_matches(self, text, source_tokens):
        return []


class ResearchPackage:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        manifest = load(self.directory / "manifest.json")
        if manifest.get("integrated") is not False or manifest.get("runtime_approved") is not False:
            raise ValueError("Expected a frozen, unapproved research package")
        seen = set()
        for row in manifest["files"]:
            if Path(row["name"]).name != row["name"] or row["name"] in seen:
                raise ValueError("Unsafe or duplicate manifest member")
            seen.add(row["name"])
            path = self.directory / row["name"]
            if path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
                raise ValueError(f"Package integrity mismatch: {row['name']}")
        self.manifest_sha256 = digest(self.directory / "manifest.json")
        self.concepts = unique(load(self.directory / "concepts.json")["concepts"], "id")
        self.forms = unique(load(self.directory / "form_decisions.json")["forms"], "form_id")
        self.views = {lang: load(self.directory / f"normalization_{lang}.json") for lang in ("en", "es")}
        self.translations = load(self.directory / "translation_en_es.json")["entries"]
        self.restrictions = load(self.directory / "restrictions.json")
        if len(self.concepts) != 657 or len(self.forms) != 567 or len(self.translations) != 657:
            raise ValueError("Incomplete package")
        for lang, view in self.views.items():
            entries = unique(view["entries"], "concept_id")
            if set(entries) != set(self.concepts):
                raise ValueError("Language view lost concepts")
            for cid, entry in entries.items():
                if entry["canonical"] != self.concepts[cid]["canonical_en" if lang == "en" else "preferred_es"]:
                    raise ValueError("Language view changes canonical form")
                if entry["automatic_substitution_approved"] is not False:
                    raise ValueError("Unexpected substitution approval")
                for fid in entry["review_alternative_ids"]:
                    f = self.forms[fid]
                    if (f["concept_id"], f["language"], f["bucket"], f["query_review_eligible"]) != (
                            cid, lang, "reviewable_variant", True):
                        raise ValueError("Unsafe alternative in review selection")

    def document(self, language):
        if language not in self.views:
            raise ValueError("Language must be explicit en or es")
        # Runtime-shaped ONLY in memory, not exported or passed to app configuration.
        return {"name": "LAB ONLY: frozen package observation", "terms": [
            {"canonical": entry["canonical"], "auto_apply": "suggest",
             "aliases": [self.forms[fid]["form"] for fid in entry["review_alternative_ids"]]}
            for entry in self.views[language]["entries"]]}

    def observer(self, language, fuzzy=False):
        cls = TerminologyNormalizer if fuzzy else ExactObservationNormalizer
        return cls.from_documents([self.document(language)], NormalizerConfig())

    def concept_for_candidate(self, language, candidate):
        return next(c["id"] for c in self.concepts.values()
                    if _tokens(c["canonical_en" if language == "en" else "preferred_es"]) == _tokens(candidate))

    def annotate(self, language, suggestion):
        row = asdict(suggestion)
        cid = self.concept_for_candidate(language, row["candidate"])
        c = self.concepts[cid]
        row.update(concept_id=cid, reference_context_required=c["reference_context_required"],
                   clinical_context=c["clinical_context"],
                   requires_clinical_distinction_review=bool(c["clinical_distinction_guards"]),
                   approval="not_approved_do_not_rewrite")
        return row


def strict_observe(observer, segment_id, text):
    """Keep all native candidates as diagnostics; controlled output is raw bytes/text."""
    started = time.perf_counter_ns()
    native = observer.normalize(segment_id, text)
    elapsed = (time.perf_counter_ns() - started) / 1_000_000
    return {"controlled_text": text, "native_candidate_text": native.normalized_text,
            "native_corrections": [asdict(c) for c in native.corrections],
            "suggestions": native.suggestions, "normalization_ms": elapsed}


def full_span_target(package, language, text, suggestions, cid):
    # Used on isolated synthetic probes; offsets therefore have an exact oracle.
    return any(package.concept_for_candidate(language, s.candidate) == cid and
               s.start == 0 and s.end == len(text) and not s.cross_segment for s in suggestions)


def validate_surfaces(package):
    observers = {lang: package.observer(lang) for lang in ("en", "es")}
    rows, failures = [], []
    for lang, field in [("en", "canonical_en"), ("es", "preferred_es")]:
        for c in package.concepts.values():
            observer = observers[lang]; observer.reset(); text = c[field]
            result = strict_observe(observer, c["id"], text)
            found = full_span_target(package, lang, text, result["suggestions"], c["id"])
            row = dict(kind="canonical", id=c["id"], language=lang, text=text,
                       full_span_target_found=found, controlled_text_identical=result["controlled_text"] == text,
                       native_spacing_changes=len(result["native_corrections"]))
            rows.append(row)
            if not found or result["controlled_text"] != text:
                failures.append(row)
    for f in package.forms.values():
        lang, text, cid = f["language"], f["form"], f["concept_id"]
        observer = observers[lang]; observer.reset()
        result = strict_observe(observer, f["form_id"], text)
        found = full_span_target(package, lang, text, result["suggestions"], cid)
        c = package.concepts[cid]
        # A held alias may be graphically identical to its canonical form; this
        # does not authorize the alias expansion, but canonical recognition exists.
        identity = _tokens(text) == _tokens(c["canonical_en" if lang == "en" else "preferred_es"])
        expected = f["query_review_eligible"] or identity
        row = dict(kind="alternative", id=f["form_id"], language=lang, text=text, bucket=f["bucket"],
                   expected_full_span_target=expected, canonical_graphic_identity=identity,
                   full_span_target_found=found, controlled_text_identical=result["controlled_text"] == text)
        rows.append(row)
        if found != expected or result["controlled_text"] != text:
            failures.append(row)
    return dict(probes=len(rows), canonical_probes=1314, alternative_probes=567,
                failures=failures, passed=not failures, rows=rows,
                scope="Synthetic graph/form consistency, not independent ASR or clinical accuracy.")


def adversarial_cases(package):
    # Fixed negatives/oracles, independent of the speech references. They are
    # examples of terminology use, not treatment recommendations.
    cases = [
        ("en", "No hypertension; potassium is not low.", "negation", []),
        ("es", "No hay hipertensión ni hipopotasemia.", "negation", []),
        ("en", "The record says 5 mg, not 50 mg; BP <140/90 mmHg.", "dose_comparator", []),
        ("es", "Constan 5 mg, no 50 mg; presión arterial ≥140/90 mmHg.", "dose_comparator", []),
        ("en", "Keep -5%, 0.5 mg, 5 µg/dL and 5 mg/dL distinct.", "unit_prefix_sign", []),
        ("es", "Conservar −5%, 0,5 mg, 5 μg/dL y 5 mg/dL.", "unit_prefix_sign", []),
        ("en", "MRA is undefined in this sentence.", "ambiguous_abbreviation", ["MRA"]),
        ("es", "ECA no tiene definición local.", "ambiguous_abbreviation", ["ECA"]),
        ("es", "PAD no tiene definición local.", "ambiguous_abbreviation", ["PAD"]),
        ("en", "PAD has no local definition.", "ambiguous_abbreviation", ["PAD"]),
        ("en", "HR, PA, HRV, RR and CI need local definitions.", "ambiguous_abbreviation", ["HR", "PA", "HRV", "RR", "CI"]),
        ("es", "IC, RAR y PA necesitan definición local.", "ambiguous_abbreviation", ["IC", "RAR", "PA"]),
        ("es", "El coordinador conjunto organizó la reunión.", "rejected_alias", ["coordinador conjunto"]),
        ("es", "Se discutió la relación presión-natriuresis.", "rejected_alias", ["relación presión-natriuresis"]),
        ("es", "La carga de medicación se preparó en farmacia.", "rejected_alias", ["carga de medicación"]),
        ("es", "La frase hipertensión farmacológica resulta ambigua.", "rejected_alias", ["hipertensión farmacológica"]),
        ("es", "La prueba de captopril necesita especificar el protocolo.", "diagnostic_purpose", ["prueba de captopril"]),
        ("en", "The 2025 ACC/AHA guideline needs an explicit topic.", "reference_identity", ["2025 ACC/AHA guideline"]),
        ("en", "SPYRAL HTN-OFF MED and SPYRAL HTN-ON MED are different arms.", "trial_arm", []),
        ("en", "Keep SPRINT, ESPRIT, STEP and STEP-1 distinct.", "trial_identity", []),
        ("en", "ACE and ACE2; AT1 and AT2; HFrEF and HFpEF.", "subtype_identity", []),
        ("en", "Left is not right, and severe is not serious.", "clinical_polarity", []),
        ("es", "Sistólica no es diastólica; alta no es baja.", "clinical_polarity", []),
        ("en", "She will map the route and check the HR policy.", "nonmedical_negative", ["HR"]),
        ("en", "The orange suitcase is beside the wooden chair.", "nonmedical_negative", []),
        ("es", "La maleta naranja está junto a la silla de madera.", "nonmedical_negative", []),
        ("en", "  No edema,please;keep 5 mg.  ", "spacing_native_only", []),
        ("es", "  No edema,por favor;conservar 5 mg.  ", "spacing_native_only", []),
        ("en", "The transcript contains hyper tenson.", "synthetic_split_typo", []),
        ("en", "They discussed primary aldosteronizm.", "synthetic_typo", []),
    ]
    rows = [dict(id=f"A{i:03d}", language=lang, text=text, category=category, protected_forms=protected,
                 origin="fixed_constructed_case_not_recorded_speech")
            for i, (lang, text, category, protected) in enumerate(cases, 1)]
    for pair in package.restrictions["near_form_decisions"]:
        for suffix in ("a", "b"):
            rows.append(dict(id=pair["review_id"] + suffix, language=pair["language"], text=pair["form_" + suffix],
                             category="near_form_pair", protected_forms=[],
                             forbidden_concept_id=pair["concept_" + ("b" if suffix == "a" else "a")],
                             expected_concept_id=pair["concept_" + suffix], origin="inherited_near_form_guard"))
    return rows


def evaluate_cases(package, cases):
    observers = {lang: package.observer(lang) for lang in ("en", "es")}
    rows = []
    for case in cases:
        obs = observers[case["language"]]; obs.reset()
        result = strict_observe(obs, case["id"], case["text"])
        suggestions = [package.annotate(case["language"], s) for s in result["suggestions"]]
        violations = []
        for s in suggestions:
            if s["source"] in case["protected_forms"]:
                violations.append(dict(kind="unconditional_protected_form_suggestion", suggestion=s))
            if case.get("forbidden_concept_id") == s["concept_id"] and s["start"] == 0 and s["end"] == len(case["text"]):
                violations.append(dict(kind="wrong_near_pair_target", suggestion=s))
        unchanged = result["controlled_text"] == case["text"]
        rows.append(dict(**case, controlled_text=result["controlled_text"], unchanged=unchanged,
                         measurement_signatures_preserved=measurement_signatures(result["controlled_text"]) == measurement_signatures(case["text"]),
                         native_candidate_text=result["native_candidate_text"], native_corrections=result["native_corrections"],
                         suggestions=suggestions, violations=violations, normalization_ms=result["normalization_ms"]))
    return dict(cases=len(rows), failed_cases=[r["id"] for r in rows if not r["unchanged"] or r["violations"]], rows=rows,
                policy="Exact observation only. Protected spans test suggestion routing; unchanged output is enforced, not evidence of ASR improvement.")


def fuzzy_diagnostics(package, cases):
    # The default suggest matcher is deliberately tested separately. It is not
    # silently substituted for the approved exact-observation laboratory profile.
    rows = []
    selected = [r for r in cases if r["origin"] == "fixed_constructed_case_not_recorded_speech"]
    for case in selected:
        started = time.perf_counter_ns()
        result = shadow(case["text"], case["text"], package.document(case["language"]), case["id"])
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        if result["status"] == "blocked":
            rows.append(dict(id=case["id"], blocked=result["reason"])); continue
        fuzzy = [s for s in result["suggestions"] if "fuzzy" in s["rule"]]
        for suggestion in fuzzy:
            cid = package.concept_for_candidate(case["language"], suggestion["candidate"])
            suggestion["concept_id"] = cid
            suggestion["review_required"] = True
        rows.append(dict(id=case["id"], language=case["language"], input=case["text"],
                         native_candidate_text=result["candidate_text"], native_corrections=result["corrections"],
                         fuzzy_suggestions=fuzzy, suggestions_total=len(result["suggestions"]),
                         wall_ms_including_load_and_metrics=elapsed, controlled_text=case["text"],
                         note="Existing shadow permits spacing; this validation's stricter controlled output remains the original input."))
        if len(rows) % 5 == 0:
            print(f"Default fuzzy diagnostic: {len(rows)}/{len(selected)} cases", flush=True)
    return dict(profile="existing normalizer with all 657 terms in suggest and default .90/.86 thresholds",
                cases=rows, fuzzy_suggestions_total=sum(len(r.get("fuzzy_suggestions", [])) for r in rows),
                policy="Unadjudicated diagnostics only; no fuzzy suggestion or replacement is approved.")


def timing(values):
    ordered = sorted(values)
    return dict(n=len(values), median_ms=statistics.median(values) if values else None,
                p95_ms=ordered[min(len(ordered)-1, int(.95 * len(ordered)))] if ordered else None,
                max_ms=max(values) if values else None)


def cached_corpus(package, out):
    inputs = load(CACHED / "inputs/inputs.json")
    provenance, rows, input_checks = [], [], []
    doc = package.document("en")
    reference_inventories = {}
    for source in inputs:
        for field, expected in [("audio_path", "audio_sha256"), ("reference_path", "reference_sha256")]:
            path = Path(source[field])
            observed = digest(path)
            if observed != source[expected]:
                raise ValueError(f"Original corpus has changed: {path}")
            input_checks.append(dict(path=str(path), sha256=observed, matches_cached_input=True))
    for model in MODELS:
        for source in inputs:
            sid = source["id"]; folder = CACHED / "models" / model / sid
            record = load(folder / "result.json")
            raw = (folder / "hypothesis.raw.txt").read_text(encoding="utf-8-sig")
            reference = Path(source["reference_path"]).read_text(encoding="utf-8-sig")
            if record["status"] != "completed" or record["variant"] != "baseline":
                raise ValueError("Only completed comparable baseline runs are accepted")
            if record["hypothesis_raw"] != raw or record["reference_raw"] != reference:
                raise ValueError("Cached raw hypothesis/reference mismatch")
            if record["audio_sha256"] != source["audio_sha256"] or record["reference_sha256"] != source["reference_sha256"]:
                raise ValueError("Cached corpus provenance mismatch")
            if digest(folder / "reference.original.txt") != source["reference_sha256"]:
                raise ValueError("Cached original reference copy differs")
            if "".join(s["text"] for s in record["segments"]) != raw:
                raise ValueError("ASR segments do not exactly reconstruct the hypothesis")
            observer = package.observer("en"); identity = IdentityNormalizer()
            controlled, segment_rows, elapsed, base_elapsed = [], [], [], []
            for segment in record["segments"]:
                text = segment["text"]; key = f"{model}:{sid}:{segment['id']}"
                started = time.perf_counter_ns(); base = identity.normalize(key, text)
                base_elapsed.append((time.perf_counter_ns()-started)/1_000_000)
                result = strict_observe(observer, key, text)
                if base.normalized_text != text:
                    raise ValueError("Identity baseline changed text")
                controlled.append(result["controlled_text"]); elapsed.append(result["normalization_ms"])
                segment_rows.append(dict(id=key, raw_text=text, controlled_text=result["controlled_text"],
                    start=segment["start"], end=segment["end"],
                    native_corrections=result["native_corrections"],
                    suggestions=[package.annotate("en", s) for s in result["suggestions"]],
                    normalization_ms=result["normalization_ms"]))
            candidate = "".join(controlled)
            baseline_metrics, observed_metrics = metrics(reference, raw), metrics(reference, candidate)
            if baseline_metrics["word_errors"] != record["metrics"]["word_errors"]:
                raise ValueError("Recomputed baseline WER differs from saved inference")
            if sid not in reference_inventories:
                # Read-only counting; no reference is ever normalized/replaced.
                reference_inventories[sid] = term_inventory(reference, reference, doc["terms"])
            inventory = term_inventory(reference, raw, doc["terms"])
            row = dict(model=model, sample_id=sid, audio_duration_s=record["audio_duration_s"],
                       reference_status=source["reference_status"],
                       baseline=baseline_metrics, with_package_controlled=observed_metrics,
                       text_identical=candidate == raw, lexical_occurrence_deficit=sum(r["occurrence_deficit"] for r in inventory),
                       lexical_occurrence_excess=sum(r["occurrence_excess"] for r in inventory),
                       matched_concepts_in_hypothesis=sum(r["hypothesis_occurrences"] > 0 for r in inventory),
                       suggestions=sum(len(r["suggestions"]) for r in segment_rows),
                       nonidentity_suggestions=sum(s["source"] != s["candidate"] for r in segment_rows for s in r["suggestions"]),
                       native_spacing_corrections=sum(len(r["native_corrections"]) for r in segment_rows),
                       timing=timing(elapsed), identity_timing=timing(base_elapsed),
                       segmentation="Saved offline ASR segments, not real READY or live latency",
                       clinical_false_positive_rate=None, clinical_false_negative_rate=None,
                       reason_unmeasured="No independent clinical labels of suggestions; lexical deficits/excesses are not certified clinical errors.")
            rows.append(row)
            save(out, f"corpus_{model}_{sid}.json", dict(summary=row, segments=segment_rows, term_inventory=inventory))
            provenance += [dict(path=str(path), sha256=digest(path)) for path in
                           [folder / "result.json", folder / "hypothesis.raw.txt", folder / "reference.original.txt",
                            folder.parent / "environment.json"]]
            print(f"Cached corpus: {model}/{sid}; {len(segment_rows)} segments; WER {baseline_metrics['wer']:.4%}", flush=True)
    aggregate = []
    for model in MODELS:
        subset = [r for r in rows if r["model"] == model]
        words = sum(r["baseline"]["reference_words"] for r in subset)
        chars = sum(r["baseline"]["reference_characters"] for r in subset)
        errors = sum(r["baseline"]["word_errors"] for r in subset)
        char_errors = sum(r["baseline"]["character_errors"] for r in subset)
        aggregate.append(dict(model=model, reference_words=words, word_errors=errors,
                              baseline_wer=errors/words, with_package_controlled_wer=errors/words,
                              baseline_cer=char_errors/chars, with_package_controlled_cer=char_errors/chars,
                              suggestions=sum(r["suggestions"] for r in subset),
                              nonidentity_suggestions=sum(r["nonidentity_suggestions"] for r in subset),
                              lexical_occurrence_deficit=sum(r["lexical_occurrence_deficit"] for r in subset),
                              lexical_occurrence_excess=sum(r["lexical_occurrence_excess"] for r in subset),
                              all_controlled_outputs_identical=all(r["text_identical"] for r in subset)))
    return dict(rows=rows, aggregate=aggregate, input_hash_checks=input_checks, provenance=provenance,
                unique_audio_samples=len(inputs), unique_audio_duration_s=sum(s["audio"]["duration_s"] for s in inputs),
                separate_model_outputs=len(rows), new_audio_inference_performed=False,
                spanish_recorded_speech_available=False, provider_translation_evaluated=False,
                causality_limit="Identical WER is guaranteed by preserving raw text; this is no evidence of improved ASR or clinical translation.")


def preservation(out):
    baseline = load(out / "baseline.json")
    strict_prefixes = ("research/", "glossaries/", "logs/trad_lab/20261020T074247Z/evaluation/", "C:/TRAD-LAB/corpus/")
    essential = {"trad_lab/glossary.py", "trad_lab/metrics.py", "app/captions/terminology_normalizer.py", "app/captions/identity_normalizer.py"}
    drift = []; strict = 0
    for row in baseline["files"]:
        name = row["path"]; path = Path(name) if Path(name).is_absolute() else ROOT / name
        observed = digest(path) if path.is_file() else None
        protected = name.startswith(strict_prefixes) or name in essential
        strict += int(protected)
        if observed != row["sha256"]:
            if protected:
                raise ValueError(f"Protected original/evidence changed: {name}")
            drift.append(dict(path=name, before_sha256=row["sha256"], observed_sha256=observed,
                              decision="outside_this_task_write_boundary_not_reverted"))
    return dict(files_checked=len(baseline["files"]), strictly_protected_files_checked=strict,
                all_original_glossaries_research_package_corpus_cached_asr_unchanged=True,
                other_snapshot_drift=drift,
                authored_paths=["trad_lab/glossary_package.py", "tests/test_glossary_package.py", str(out.relative_to(ROOT)) + "/"],
                app_code_config_services_and_translation_not_modified_or_started=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    out = RESULTS
    if not (out / "baseline.json").is_file() or (out / "summary.json").exists():
        raise SystemExit("Requires a fresh results directory with a pre-write baseline; refuses to overwrite a completed run.")
    package = ResearchPackage(PACKAGE)
    print("Package manifest verified; compiling isolated laboratory views", flush=True)
    started = time.perf_counter()
    surface = validate_surfaces(package); save(out, "surface_checks.json", surface)
    print(f"Surface probes: {surface['probes']}; failures: {len(surface['failures'])}", flush=True)
    cases = adversarial_cases(package); save(out, "adversarial_cases.json", cases)
    adversarial = evaluate_cases(package, cases); save(out, "adversarial_results.json", adversarial)
    corpus = cached_corpus(package, out); save(out, "corpus_comparison.json", corpus)
    fuzzy = fuzzy_diagnostics(package, cases); save(out, "fuzzy_diagnostics.json", fuzzy)
    commands = [
        [sys.executable, "-B", "-m", "unittest", "tests.test_glossary_package", "tests.test_trad_lab", "tests.test_terminology_normalizer", "-v"],
        [sys.executable, "-B", str(PACKAGE / "test_package.py")],
    ]
    test_results = []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        test_results.append(dict(command=command, returncode=result.returncode, output=result.stdout + result.stderr))
    save(out, "test_results.json", test_results)
    protected = preservation(out); save(out, "preservation.json", protected)
    summary = dict(completed_at_utc=datetime.now(timezone.utc).isoformat(), status="laboratory_validation_complete_not_integrated",
        package_manifest_sha256=package.manifest_sha256,
        data_and_exact_observation_checks_passed=surface["passed"] and not adversarial["failed_cases"] and
            all(r["returncode"] == 0 for r in test_results) and all(r["text_identical"] for r in corpus["rows"]),
        surface_probes=surface["probes"], surface_failures=len(surface["failures"]),
        adversarial_cases=adversarial["cases"], adversarial_failed_cases=adversarial["failed_cases"],
        corpus_aggregate=corpus["aggregate"], fuzzy_suggestions_requiring_review=fuzzy["fuzzy_suggestions_total"],
        runtime_activation_approved=False, automatic_substitutions_approved=0, integration_performed=False,
        new_asr_inference_performed=False, external_calls=0, services_started=0,
        spanish_speech_and_provider_translation_validated=False,
        independent_clinician_review="not_performed", validation_wall_s=time.perf_counter()-started,
        next_gate="Review diagnostic findings and any future application design separately; no operational activation follows from this report.")
    save(out, "summary.json", summary)
    save(out, "manifest.json", dict(files=[dict(name=f.name, bytes=f.stat().st_size, sha256=digest(f)) for f in sorted(out.iterdir())
                                           if f.is_file() and f.name != "manifest.json"],
                                    validator_sha256=digest(Path(__file__)), tests_sha256=digest(ROOT / "tests/test_glossary_package.py"),
                                    input_package_manifest_sha256=package.manifest_sha256, integration_performed=False))
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0 if summary["data_and_exact_observation_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
