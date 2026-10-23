"""Laboratory-only context guards, with frozen terms/thresholds and raw inputs."""
from collections import Counter
from dataclasses import asdict
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
import json
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRIOR = HERE.parent / "tolerance_trial_10_v1"
sys.path.insert(0, str(PRIOR))
sys.path.insert(0, str(ROOT))
import evaluate_trial as prior
from app.captions.terminology_normalizer import TerminologyNormalizer, NormalizerConfig, _tokens
from trad_lab.metrics import tokens, metrics, word_alignment, measurement_signatures, NEGATIONS, NUMBER_WORDS, UNITS

FUNCTION_WORDS = set("a an the by of with without and or for to from in on at into onto upon over under between during through before after as than that which who is are was were be been being has have had do does did this these those it its their our your his her any each both either neither not no never nor only also then if while when where so yet can could may might must should will would".split())
CONTRAST_GROUPS = [
    {"primary", "secondary"}, {"systolic", "diastolic"}, {"sodium", "potassium"},
    {"left", "right"}, {"high", "low"}, {"treated", "untreated"}, {"controlled", "uncontrolled"},
    {"american", "european"}, {"event", "events"}, {"receptor", "receptors"},
    {"inhibitor", "inhibitors"}, {"salt", "salts"},
]


def save(name, data):
    if Path(name).name != name:
        raise ValueError("Write boundary is this new directory")
    (HERE/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def ratio(a, b):
    return SequenceMatcher(None, a, b).ratio()


def quantity_signature(text):
    return dict(number_words=[w for w in tokens(text) if w in NUMBER_WORDS],
                raw_measurements=[m["value"] for m in measurement_signatures(text)],
                unit_tokens=[w for w in tokens(text) if w in UNITS])


def token_alignment(source, target):
    """Consume every token; permit spelling fragments, never a dropped neighbor."""
    @lru_cache(None)
    def walk(i, j):
        if j == len(target):
            return () if i == len(source) else None
        for width in (1, 2, 3):
            group = source[i:i+width]
            if len(group) != width:
                continue
            joined = "".join(group); word = target[j]
            if word in FUNCTION_WORDS or word in NUMBER_WORDS or word in UNITS or any(c.isdigit() for c in word):
                if width != 1 or joined != word:
                    continue
            elif joined != word:
                if ratio(joined, word) < .65:
                    continue
                if width > 1 and any(ratio(fragment, word) >= .85 for fragment in group):
                    # A nearly complete word plus another token is not a split.
                    continue
            rest = walk(i+width, j+1)
            if rest is not None:
                return ((tuple(group), word),)+rest
        return None
    return walk(0, 0)


def guard_span(text, start, end, canonical):
    source = text[start:end]; a, b = _tokens(source), _tokens(canonical)
    reasons = []
    if not (0 <= start < end <= len(text)):
        return dict(accepted=False, reasons=["invalid_span"], alignment=None)
    if (start and (text[start-1].isalnum() or text[start-1] in "_'’")) or (
            end < len(text) and (text[end].isalnum() or text[end] in "_'’")):
        reasons.append("whole_word_or_identifier_boundary")
    if [w for w in a if w in FUNCTION_WORDS] != [w for w in b if w in FUNCTION_WORDS]:
        reasons.append("function_word_sequence_changed")
    if [w for w in tokens(source) if w in NEGATIONS] != [w for w in tokens(canonical) if w in NEGATIONS]:
        reasons.append("negation_changed")
    if quantity_signature(source) != quantity_signature(canonical):
        reasons.append("literal_quantity_or_unit_changed")
    for group in CONTRAST_GROUPS:
        incoming, outgoing = [w for w in a if w in group], [w for w in b if w in group]
        if incoming and incoming != outgoing:
            reasons.append("opposed_qualifier_or_grammatical_number_changed")
            break
    for word in a:
        for prefix in ("non", "un"):
            if word.startswith(prefix) and word[len(prefix):] in b and word not in b:
                reasons.append("morphological_negation_changed")
    anchors = [w for w in a if w in b and len(w) >= 3 and w not in FUNCTION_WORDS]
    if not anchors:
        reasons.append("no_unchanged_lexical_anchor")
    alignment = token_alignment(a, b)
    if alignment is None:
        reasons.append("no_lossless_token_alignment")
    return dict(accepted=not reasons, reasons=sorted(set(reasons)), alignment=alignment)


class ContextNormalizer(TerminologyNormalizer):
    """Never used by app/: preselection guards are experimental and local."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.guard_audit = []

    def _screen_matches(self, text, matches):
        accepted = []
        for match in matches:
            guard = guard_span(text, match.start, match.end, match.term.canonical)
            if guard["accepted"]:
                accepted.append(match)
            else:
                self.guard_audit.append(dict(source=text[match.start:match.end], canonical=match.term.canonical,
                    start=match.start, end=match.end, confidence=match.confidence, action=match.action, rule=match.rule, **guard))
        return accepted

    def _exact_matches(self, text, source_tokens):
        return self._screen_matches(text,super()._exact_matches(text,source_tokens))

    def _fuzzy_matches(self, text, source_tokens):
        return self._screen_matches(text,super()._fuzzy_matches(text,source_tokens))


def document(selected, thresholds):
    terms=[]
    for item in selected:
        threshold=thresholds[item["concept_id"]]
        term=dict(canonical=item["canonical_en"], auto_apply="exact" if threshold is None else "fuzzy")
        if threshold is not None:
            term.update(auto_threshold=threshold, suggest_threshold=min(.86,threshold-.01))
        terms.append(term)
    return dict(terms=terms)


def candidate(text, selected, thresholds, profile="preselection_guards"):
    cls=ContextNormalizer if profile == "preselection_guards" else TerminologyNormalizer
    obj=cls.from_documents([document(selected,thresholds)],NormalizerConfig())
    started=time.perf_counter_ns()
    native=obj.normalize("context-lab",text)
    changes=[asdict(c) for c in native.corrections if c.rule != "deterministic_spacing"]
    blocked=list(getattr(obj,"guard_audit",[]))
    if profile == "postselection_veto":
        kept=[]
        for change in changes:
            verdict=guard_span(text,change["start"],change["end"],change["canonical"])
            if verdict["accepted"]:
                kept.append(change)
            else:
                blocked.append(dict(**change,**verdict))
        changes=kept
    output=text
    for change in sorted(changes,key=lambda c:(c["start"],c["end"]),reverse=True):
        output=output[:change["start"]]+change["replacement"]+output[change["end"]:]
    return dict(text=output,changes=changes,blocked=blocked,controlled_text=text,
                wall_ms=(time.perf_counter_ns()-started)/1_000_000,
                policy="New research artifacts only; never sent to LIVE")


def verify_inputs():
    protocol=prior.load(HERE/"protocol.json")
    for name,digest in protocol["frozen_inputs"].items():
        if prior.sha(PRIOR/name) != digest:
            raise ValueError("Previous experiment changed: "+name)
    for directory in [PRIOR,HERE.parent/"integration_candidate",HERE.parent/"laboratory_validation_v1"]:
        manifest=prior.load(directory/"manifest.json")
        for row in manifest["files"]:
            path=directory/row["name"]
            if path.stat().st_size != row["bytes"] or prior.sha(path) != row["sha256"]:
                raise ValueError("Prior manifest mismatch: "+str(path))


def prior_constructed(selected, thresholds):
    cases=prior.load(PRIOR/"constructed_cases.json")
    exclude=set(prior.load(PRIOR/"checking_overlap_audit.json")["exact_duplicate_checking_case_ids"])
    results=[]
    for item in selected:
        cid=item["concept_id"]
        subset=[c for c in cases if c["concept_id"]==cid and c["split"]=="synthetic_checking" and c["case_id"] not in exclude]
        for profile in ["individualized","postselection_veto","preselection_guards"]:
            rows=[]
            for case in subset:
                r=candidate(case["text"],[item],{cid:thresholds[cid]},profile)
                rows.append(dict(case_id=case["case_id"],triggered=any(c["rule"]=="glossary_fuzzy" for c in r["changes"]),
                    recovered=tokens(r["text"])==tokens(case.get("intended","")) if case["positive"] else False,
                    output=r["text"],changes=r["changes"],blocked=r["blocked"]))
            results.append(dict(concept_id=cid,profile=profile,**prior.score_cases(rows,subset),results=rows))
    return results


def make_context_cases(selected):
    frozen=prior.load(PRIOR/"synthetic_checking.json")
    old_cases={c["case_id"]:c for c in prior.load(PRIOR/"constructed_cases.json")}
    rows=[]
    suffixes=[" by this confirmatory test."," with the control group."," for patients."," patients arrived."," children were assessed."," yesterday."]
    for item in selected:
        cid=item["concept_id"]; canonical=item["canonical_en"]
        old=next(r for r in frozen if r["concept_id"]==cid and r["profile"]=="individualized")
        variant_case=next(r for r in old["results"] if r["recovered"])
        variant=old_cases[variant_case["case_id"]]["text"]
        for suffix in suffixes:
            prefix="They discussed "
            rows.append(dict(concept_id=cid,kind="neighbor_context",positive=True,
                text=prefix+variant+suffix,expected=prefix+canonical+suffix,
                original_variant_case_id=variant_case["case_id"]))
        rows.append(dict(concept_id=cid,kind="outer_negation",positive=True,text="No evidence of "+variant+" by this test.",
                         expected="No evidence of "+canonical+" by this test.",original_variant_case_id=variant_case["case_id"]))
        words=canonical.split(); cut=len(words[0])
        for inserted,kind in [(" by ","inner_function_word"),(" not ","inner_negation"),(" 5 ","inner_quantity")]:
            text=canonical[:cut]+inserted+canonical[cut:].lstrip()
            rows.append(dict(concept_id=cid,kind=kind,positive=False,text=text,expected=text))
        text="tag_"+variant
        rows.append(dict(concept_id=cid,kind="identifier_boundary",positive=False,text=text,expected=text))
        text="non"+canonical
        rows.append(dict(concept_id=cid,kind="morphological_negation",positive=False,text=text,expected=text))
    cid=next(r["concept_id"] for r in selected if r["canonical_en"]=="primary aldosteronism")
    for text,expected in [
        ("primary allosteronism by this confirmatory testing", "primary aldosteronism by this confirmatory testing"),
        ("No primary allosteronism by this test", "No primary aldosteronism by this test"),
        ("primary allosteronism patients arrived", "primary aldosteronism patients arrived"),
    ]:
        rows.append(dict(concept_id=cid,kind="known_boundary_regression",positive=True,text=text,expected=expected))
    for i,row in enumerate(rows,1):
        row["case_id"]=f"C{i:03d}"
        row["origin"]="Constructed context regression, not new audio or independent clinical validation"
    return rows


def evaluate_contexts(cases,selected,thresholds):
    rows=[]
    for profile in ["individualized","postselection_veto","preselection_guards"]:
        for case in cases:
            result=candidate(case["text"],selected,thresholds,profile)
            rows.append(dict(case_id=case["case_id"],profile=profile,positive=case["positive"],kind=case["kind"],
                text=case["text"],expected=case["expected"],output=result["text"],
                exact_expected_output=result["text"]==case["expected"],
                undesired_negative_change=(not case["positive"] and result["text"] != case["text"]),
                changes=result["changes"],blocked=result["blocked"]))
    summary=[]
    for profile in ["individualized","postselection_veto","preselection_guards"]:
        subset=[r for r in rows if r["profile"]==profile]
        pos=[r for r in subset if r["positive"]];neg=[r for r in subset if not r["positive"]]
        summary.append(dict(profile=profile,positive_cases=len(pos),positive_exact_outputs=sum(r["exact_expected_output"] for r in pos),
            negative_cases=len(neg),undesired_negative_changes=sum(r["undesired_negative_change"] for r in neg),
            failed_case_ids=[r["case_id"] for r in subset if not r["exact_expected_output"]]))
    return dict(summary=summary,rows=rows)


def compare_corpus(selected,thresholds):
    old=prior.load(PRIOR/"real_speech_checking.json")
    positions=prior.load(PRIOR/"reference_occurrences.json")
    sources=prior.load(prior.CACHED/"inputs/inputs.json")
    rows=[]; changes=[]; occurrence_rows=[]; outputs=[]
    for model in ["small","medium","large-v3-turbo"]:
        for source in sources:
            sid=source["id"];data=prior.load(prior.CACHED/"models"/model/sid/"result.json")
            raw,ref=data["hypothesis_raw"],data["reference_raw"]
            if prior.sha(source["audio_path"])!=source["audio_sha256"] or prior.sha(source["reference_path"])!=source["reference_sha256"]:
                raise ValueError("Original audio/reference changed")
            for profile in ["raw","individualized","postselection_veto","preselection_guards"]:
                result=dict(text=raw,changes=[],blocked=[],wall_ms=0) if profile=="raw" else candidate(raw,selected,thresholds,profile)
                if profile=="individualized":
                    previous=next(r for r in old["outputs"] if r["model"]==model and r["sample_id"]==sid and r["profile"]==profile)
                    if result["text"] != previous["candidate_text"]:
                        raise ValueError("Same-threshold baseline did not reproduce")
                measured=data["metrics"] if result["text"]==raw else metrics(ref,result["text"])
                hyp=tokens(result["text"]);ref_words=tokens(ref)
                mapped=prior.ref_map(ref_words,hyp,measured["word_edits"])
                rows.append(dict(model=model,sample_id=sid,profile=profile,
                    word_errors=measured["word_errors"],reference_words=measured["reference_words"],wer=measured["wer"],
                    character_errors=measured["character_errors"],reference_characters=measured["reference_characters"],
                    simulated_corrections=len(result["changes"]),wall_ms=result["wall_ms"],
                    cue_signature_changed=prior.cue_signature(raw)!=prior.cue_signature(result["text"]),
                    function_word_sequence_changed=[w for w in _tokens(raw) if w in FUNCTION_WORDS] !=
                                                   [w for w in _tokens(result["text"]) if w in FUNCTION_WORDS]))
                for change in result["changes"]:
                    changes.append(dict(model=model,sample_id=sid,profile=profile,**change))
                for position in positions:
                    if position["sample_id"]!=sid:
                        continue
                    phrase,indices=prior.extracted_span(position["ref_left"],position["ref_right"],mapped,hyp,measured["word_edits"])
                    occurrence_rows.append(dict(**position,model=model,profile=profile,observed_tokens=phrase,
                        exact_reference_form=phrase==position["reference_tokens"]))
                outputs.append(dict(model=model,sample_id=sid,profile=profile,candidate_text=result["text"],blocked=result["blocked"]))
            print(f"Reused speech comparison: {model}/{sid}",flush=True)
    aggregate=[]
    for model in ["small","medium","large-v3-turbo"]:
        for profile in ["raw","individualized","postselection_veto","preselection_guards"]:
            group=[r for r in rows if r["model"]==model and r["profile"]==profile]
            errors=sum(r["word_errors"] for r in group);words=sum(r["reference_words"] for r in group)
            aggregate.append(dict(model=model,profile=profile,word_errors=errors,reference_words=words,wer=errors/words,
                simulated_corrections=sum(r["simulated_corrections"] for r in group),
                samples_with_changed_cues=sum(r["cue_signature_changed"] for r in group),
                samples_with_changed_function_words=sum(r["function_word_sequence_changed"] for r in group)))
    return dict(rows=rows,aggregate=aggregate,changes=changes,occurrences=occurrence_rows,outputs=outputs,
                original_raw_artifacts_modified=False,new_asr_inference=False)


def preserve():
    baseline=prior.load(HERE/"baseline.json")["files"]
    strict_count=0;drift=[]
    essential={"app/captions/terminology_normalizer.py","trad_lab/metrics.py"}
    for row in baseline:
        path=Path(row["path"])
        if not path.is_absolute():path=ROOT/path
        actual=prior.sha(path) if path.is_file() else None
        strict=row["path"].startswith(("research/","glossaries/","logs/trad_lab/20261020T074247Z/evaluation/","C:/TRAD-LAB/corpus/")) or row["path"] in essential
        strict_count+=int(strict)
        if actual!=row["sha256"]:
            if strict:raise ValueError("Protected source/evidence changed: "+row["path"])
            drift.append(dict(path=row["path"],before_sha256=row["sha256"],observed_sha256=actual,action="outside_this_task_write_boundary_not_reverted"))
    return dict(files_checked=len(baseline),strictly_protected_files_checked=strict_count,
                original_glossaries_prior_research_audio_and_cached_asr_unchanged=True,
                other_snapshot_observations=drift,authored_directory=str(HERE),integration_performed=False)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if (HERE/"summary.json").exists():
        archive=HERE/"attempts/fuzzy_only_controls/summary.json"
        if sys.argv[1:] != ["--refine"] or not archive.is_file() or prior.sha(archive)!=prior.sha(HERE/"summary.json"):
            raise SystemExit("Completed comparison exists; refinement requires the archived initial pass")
    verify_inputs()
    selected=prior.load(PRIOR/"selection.json")["selected"]
    choices=prior.load(PRIOR/"threshold_decisions.json")
    thresholds={r["concept_id"]:r["selected_auto_threshold"] for r in choices}
    cases=make_context_cases(selected);save("context_cases.json",cases)
    previous=prior_constructed(selected,thresholds);save("prior_constructed_comparison.json",previous)
    contexts=evaluate_contexts(cases,selected,thresholds);save("context_comparison.json",contexts)
    corpus=compare_corpus(selected,thresholds);save("speech_comparison.json",corpus)
    per_term=[]
    for item in selected:
        counts={}
        for profile in ["raw","individualized","postselection_veto","preselection_guards"]:
            observations=[r for r in corpus["occurrences"] if r["concept_id"]==item["concept_id"] and r["profile"]==profile]
            counts[profile]=dict(observations=len(observations),exact_reference_form=sum(r["exact_reference_form"] for r in observations))
        per_term.append(dict(**item,unchanged_auto_threshold=thresholds[item["concept_id"]],results=counts,operational_approval=False))
    save("term_results.json",per_term)
    tested=subprocess.run([sys.executable,"-B",str(HERE/"test_context.py")],cwd=ROOT,capture_output=True,text=True,encoding="utf-8")
    save("test_results.json",dict(returncode=tested.returncode,output=tested.stdout+tested.stderr))
    save("preservation.json",preserve())
    summary=dict(status="same_ten_terms_context_comparison_complete",terms=10,thresholds_retuned=False,
        raw_audio_occurrences=34,model_observations=102,profiles=corpus["aggregate"],context_cases=contexts["summary"],
        prior_constructed_summary=[dict(profile=p,positive_cases=sum(r["positive_cases"] for r in previous if r["profile"]==p),
            recovered=sum(r["recovered"] for r in previous if r["profile"]==p),
            negative_cases=sum(r["negative_cases"] for r in previous if r["profile"]==p),
            negative_triggers=sum(r["negative_triggers"] for r in previous if r["profile"]==p))
            for p in ["individualized","postselection_veto","preselection_guards"]],
        unit_tests_passed=tested.returncode==0,integration_performed=False,production_code_modified=False,
        independent_speech_or_clinical_validation=False)
    save("summary.json",summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
    return tested.returncode


if __name__=="__main__":
    raise SystemExit(main())
