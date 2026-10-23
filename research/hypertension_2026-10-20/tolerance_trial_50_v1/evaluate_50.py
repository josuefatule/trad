"""Fifty NEW random terms: frozen context guards, per-term CPU-only calibration."""
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import sys
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=HERE.parent
TEN=BASE/"tolerance_trial_10_v1"
GUARD=BASE/"context_boundary_trial_10_v1"
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(TEN));sys.path.insert(0,str(GUARD))
import evaluate_context as ctx
import evaluate_trial as prior
from trad_lab.metrics import tokens, metrics, word_alignment


def save(name,data):
    if Path(name).name!=name:raise ValueError("Results remain in the new trial folder")
    (HERE/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def verify_inputs():
    protocol=prior.load(HERE/"protocol.json")
    for row in protocol["inputs"]:
        if prior.sha(ROOT/row["path"])!=row["sha256"]:
            raise ValueError("Frozen input changed: "+row["path"])
    for directory in [TEN,GUARD,BASE/"integration_candidate",BASE/"laboratory_validation_v1"]:
        for row in prior.load(directory/"manifest.json")["files"]:
            p=directory/row["name"]
            if p.stat().st_size!=row["bytes"] or prior.sha(p)!=row["sha256"]:
                raise ValueError("Prior evidence manifest mismatch: "+str(p))


def study_cases(selected):
    concepts=prior.load(BASE/"integration_candidate/concepts.json")["concepts"]
    raw=prior.make_cases(selected,concepts)
    distinctions=prior.load(BASE/"integration_candidate/restrictions.json")["clinical_distinction_guards"]
    added=[]
    for item in selected:
        name=item["canonical_en"]
        contrasts=[]
        for guard in distinctions:
            if guard["a"].casefold()==name.casefold():contrasts.append((guard["b"],"inherited_clinical_distinction"))
            if guard["b"].casefold()==name.casefold():contrasts.append((guard["a"],"inherited_clinical_distinction"))
        for a,b in [("micrograms","milligrams"),("milligrams","micrograms"),
                    ("millimoles","micromoles"),("micromoles","millimoles")]:
            if a in name:contrasts.append((name.replace(a,b),"literal_unit_prefix_contrast"))
        for a,b in [("hypokalemic","hyperkalemic"),("hypotension","hypertension"),
                    ("hypertension","hypotension"),("serious","severe"),("urinary","plasma"),
                    ("resistant","refractory"),("elevated","normal")]:
            text,count=re.subn(r"\b"+a+r"\b",b,name)
            if count:contrasts.append((text,"preserve_clinical_qualifier_no_unconditional_equivalence"))
        last=re.search(r"\b([A-Za-z]{5,})s\b$",name)
        if last and not last.group().lower().endswith(("sis","ss","ous")):
            singular=name[:last.end()-1]+name[last.end():]
            contrasts.append((singular,"preserve_explicit_grammatical_number"))
        for text,kind in contrasts:
            if tokens(text)==tokens(name):continue
            for split in ["calibration","synthetic_checking"]:
                added.append(dict(concept_id=item["concept_id"],split=split,kind=kind,positive=False,
                    text=text if split=="calibration" else "They discussed "+text+" today.",
                    origin="No-rewrite contrast; not a synonym or treatment claim"))
    raw+=added
    for i,row in enumerate(raw,1):row["case_id"]=f"F{i:05d}"
    # Exclude duplicate input/label tuples within each split, then across splits.
    seen={};effective=[];excluded=[]
    for split in ["calibration","synthetic_checking"]:
        for case in raw:
            if case["split"]!=split:continue
            key=(case["concept_id"],case["positive"],case["text"])
            if key in seen:
                excluded.append(dict(case_id=case["case_id"],duplicate_of=seen[key],split=split))
            else:
                seen[key]=case["case_id"];effective.append(case)
    return raw,effective,excluded


def run_case(case,item,threshold,guarded=True):
    result=ctx.candidate(case["text"],[item],{item["concept_id"]:threshold},
                         "preselection_guards" if guarded else "individualized")
    return dict(case_id=case["case_id"],threshold=threshold,
        recovered=(tokens(result["text"])==tokens(case["intended"])) if case["positive"] else False,
        triggered=any(c["rule"]=="glossary_fuzzy" for c in result["changes"]),
        output=result["text"],changes=result["changes"],
        guard_rejection_reasons=dict(Counter(reason for r in result["blocked"] for reason in r["reasons"])))


def calibrate(selected,cases,grid):
    decisions=[];measurements=[]
    for i,item in enumerate(selected,1):
        cid=item["concept_id"];subset=[c for c in cases if c["concept_id"]==cid and c["split"]=="calibration"]
        scores=[]
        for threshold in grid:
            rows=[run_case(c,item,threshold) for c in subset];measurements+=rows
            scores.append(dict(threshold=threshold,**prior.score_cases(rows,subset)))
        eligible=[r for r in scores if r["negative_triggers"]==0]
        best=max(eligible,key=lambda r:(r["recovered"],r["threshold"])) if eligible else None
        useful=best is not None and best["recovered"]>0
        decisions.append(dict(concept_id=cid,canonical_en=item["canonical_en"],preferred_es=item["preferred_es"],
            selected_auto_threshold=best["threshold"] if useful else None,
            mode="fuzzy_with_frozen_guards" if useful else "exact_only_no_useful_guarded_fuzzy_recovery",
            calibration_grid=scores,tested_zero_negative_points=[r["threshold"] for r in eligible],
            reason="Highest constructed recovery with zero negatives; higher threshold breaks ties" if useful else
                   "No useful positive recovery with zero negative triggers; fuzzy remains disabled in this research profile",
            guards_sha256=prior.sha(GUARD/"evaluate_context.py"),
            selection_phase="constructed_calibration_only_before_speech_checking",operational_approval=False))
        if i%10==0:print(f"Guarded calibration: {i}/50 terms",flush=True)
    return decisions,measurements


def checking(selected,cases,decisions):
    thresholds={r["concept_id"]:r["selected_auto_threshold"] for r in decisions};rows=[]
    for item in selected:
        cid=item["concept_id"];subset=[c for c in cases if c["concept_id"]==cid and c["split"]=="synthetic_checking"]
        for profile,threshold,guarded in [("uniform090_guarded",.90,True),
                ("individualized_unguarded",thresholds[cid],False),("individualized_guarded",thresholds[cid],True)]:
            result=[run_case(c,item,threshold,guarded) for c in subset]
            rows.append(dict(concept_id=cid,profile=profile,threshold=threshold,**prior.score_cases(result,subset),results=result))
    return rows


def context_cases(selected,cases,decisions,calibration):
    table={r["concept_id"]:r for r in decisions};case_index={c["case_id"]:c for c in cases};rows=[]
    for item in selected:
        cid=item["concept_id"];decision=table[cid];name=item["canonical_en"]
        candidates=[r for r in calibration if r["threshold"]==decision["selected_auto_threshold"] and r["recovered"]
                    and case_index[r["case_id"]]["concept_id"]==cid]
        variant_case=case_index[candidates[0]["case_id"]] if candidates else next(c for c in cases if
                    c["concept_id"]==cid and c["split"]=="calibration" and c["positive"])
        variant=variant_case["text"]
        for suffix in [" by this test."," with the control group."," for patients."," patients arrived."," children were assessed."," yesterday."]:
            rows.append(dict(concept_id=cid,positive=True,kind="neighbor_context",text="They discussed "+variant+suffix,
                expected="They discussed "+name+suffix,calibration_seed_case_id=variant_case["case_id"],
                calibration_repairable=bool(candidates)))
        rows.append(dict(concept_id=cid,positive=True,kind="outer_negation",text="No evidence of "+variant+" by this test.",
            expected="No evidence of "+name+" by this test.",calibration_seed_case_id=variant_case["case_id"],calibration_repairable=bool(candidates)))
        first=len(name.split()[0])
        for inserted,kind in [(" by ","inner_function_word"),(" not ","inner_negation"),(" 5 ","inner_quantity")]:
            text=name[:first]+inserted+name[first:].lstrip()
            rows.append(dict(concept_id=cid,positive=False,kind=kind,text=text,expected=text))
        for text,kind in [("tag_"+variant,"identifier_boundary"),("non"+name,"morphological_negation")]:
            rows.append(dict(concept_id=cid,positive=False,kind=kind,text=text,expected=text))
    for i,r in enumerate(rows,1):r["case_id"]=f"N{i:04d}"
    return rows


def evaluate_contexts(selected,decisions,cases):
    tuned={r["concept_id"]:r["selected_auto_threshold"] for r in decisions}
    outputs=[];summary=[]
    for profile,guarded,thresholds in [("uniform090_guarded",True,{r["concept_id"]:.90 for r in selected}),
                    ("individualized_unguarded",False,tuned),("individualized_guarded",True,tuned)]:
        group=[]
        for case in cases:
            result=ctx.candidate(case["text"],selected,thresholds,"preselection_guards" if guarded else "individualized")
            row=dict(case_id=case["case_id"],profile=profile,positive=case["positive"],
                     calibration_repairable=case.get("calibration_repairable"),text=case["text"],expected=case["expected"],
                     output=result["text"],exact_expected_output=result["text"]==case["expected"],
                     negative_changed=(not case["positive"] and result["text"]!=case["text"]),
                     changes=result["changes"],blocked=result["blocked"])
            group.append(row)
        outputs+=group
        positive=[r for r in group if r["positive"]];negative=[r for r in group if not r["positive"]]
        repairable=[r for r in positive if r["calibration_repairable"]]
        summary.append(dict(profile=profile,positive_cases=len(positive),positive_correct=sum(r["exact_expected_output"] for r in positive),
            calibration_repairable_contexts=len(repairable),repairable_contexts_correct=sum(r["exact_expected_output"] for r in repairable),
            negative_cases=len(negative),undesired_negative_changes=sum(r["negative_changed"] for r in negative),
            failed_case_ids=[r["case_id"] for r in group if not r["exact_expected_output"]]))
        print(f"Context checking: {profile}, {len(group)} cases",flush=True)
    return dict(summary=summary,rows=outputs)


def comparison_corpus(selected,decisions):
    old_ten=prior.load(TEN/"selection.json")["selected"]
    ten_thresholds={r["concept_id"]:r["selected_auto_threshold"] for r in prior.load(TEN/"threshold_decisions.json")}
    new_thresholds={r["concept_id"]:r["selected_auto_threshold"] for r in decisions}
    combined=old_ten+selected;combined_thresholds=dict(ten_thresholds,**new_thresholds)
    sources=prior.load(prior.CACHED/"inputs/inputs.json");positions=prior.occurrences(combined,sources)
    save("reference_occurrences.json",positions)
    previous=prior.load(GUARD/"speech_comparison.json")
    profiles=["raw","previous10_guarded","new50_uniform090_guarded","new50_individualized_unguarded",
              "new50_individualized_guarded","combined60_individualized_guarded"]
    rows=[];outputs=[];changes=[];observations=[]
    for model in ["small","medium","large-v3-turbo"]:
        for sample in sources:
            sid=sample["id"];path=prior.CACHED/"models"/model/sid/"result.json";d=prior.load(path)
            raw,ref=d["hypothesis_raw"],d["reference_raw"]
            if d["variant"]!="baseline" or d["status"]!="completed" or ref!=sample["reference_raw"]:
                raise ValueError("Incomparable cached baseline")
            if raw!=(path.parent/"hypothesis.raw.txt").read_text(encoding="utf-8-sig"):
                raise ValueError("Changed cached hypothesis")
            for field,expected in [("audio_path","audio_sha256"),("reference_path","reference_sha256")]:
                if prior.sha(sample[field])!=sample[expected]:raise ValueError("Original audio/reference changed")
            metric_cache={raw:d["metrics"]}
            for profile in profiles:
                if profile=="raw":result=dict(text=raw,changes=[],blocked=[],wall_ms=0)
                elif profile=="previous10_guarded":
                    old=next(r for r in previous["outputs"] if r["model"]==model and r["sample_id"]==sid and r["profile"]=="preselection_guards")
                    old_changes=[r for r in previous["changes"] if r["model"]==model and r["sample_id"]==sid and r["profile"]=="preselection_guards"]
                    result=dict(text=old["candidate_text"],changes=old_changes,blocked=old["blocked"],wall_ms=None)
                else:
                    terms=combined if profile=="combined60_individualized_guarded" else selected
                    thresholds=combined_thresholds if profile=="combined60_individualized_guarded" else (
                        {r["concept_id"]:.90 for r in selected} if profile=="new50_uniform090_guarded" else new_thresholds)
                    result=ctx.candidate(raw,terms,thresholds,"individualized" if profile=="new50_individualized_unguarded" else "preselection_guards")
                text=result["text"]
                if text not in metric_cache:metric_cache[text]=metrics(ref,text)
                measured=metric_cache[text];hyp=tokens(text);ref_words=tokens(ref)
                mapped=prior.ref_map(ref_words,hyp,measured["word_edits"])
                before_functions=[w for w in ctx._tokens(raw) if w in ctx.FUNCTION_WORDS]
                after_functions=[w for w in ctx._tokens(text) if w in ctx.FUNCTION_WORDS]
                rows.append(dict(model=model,sample_id=sid,profile=profile,word_errors=measured["word_errors"],
                    reference_words=measured["reference_words"],wer=measured["wer"],
                    character_errors=measured["character_errors"],reference_characters=measured["reference_characters"],
                    simulated_changes=len(result["changes"]),wall_ms=result["wall_ms"],
                    cue_signature_changed=prior.cue_signature(raw)!=prior.cue_signature(text),
                    function_word_sequence_changed=before_functions!=after_functions))
                for change in result["changes"]:
                    if profile=="previous10_guarded":change={k:v for k,v in change.items() if k not in ["model","sample_id","profile"]}
                    changes.append(dict(model=model,sample_id=sid,profile=profile,**change))
                for position in positions:
                    if position["sample_id"]!=sid:continue
                    phrase,indices=prior.extracted_span(position["ref_left"],position["ref_right"],mapped,hyp,measured["word_edits"])
                    observations.append(dict(**position,model=model,profile=profile,observed_tokens=phrase,
                        exact_reference_form=phrase==position["reference_tokens"]))
                outputs.append(dict(model=model,sample_id=sid,profile=profile,candidate_text=text,
                    original_hypothesis_sha256=prior.sha(path.parent/"hypothesis.raw.txt"),blocked=result["blocked"]))
            print(f"Cached speech comparison: {model}/{sid}",flush=True)
    aggregate=[]
    for model in ["small","medium","large-v3-turbo"]:
        for profile in profiles:
            items=[r for r in rows if r["model"]==model and r["profile"]==profile]
            errors=sum(r["word_errors"] for r in items);words=sum(r["reference_words"] for r in items)
            aggregate.append(dict(model=model,profile=profile,word_errors=errors,reference_words=words,wer=errors/words,
                simulated_changes=sum(r["simulated_changes"] for r in items),
                samples_with_changed_cues=sum(r["cue_signature_changed"] for r in items),
                samples_with_changed_function_words=sum(r["function_word_sequence_changed"] for r in items)))
    return dict(rows=rows,aggregate=aggregate,changes=changes,outputs=outputs,occurrences=observations,
                unique_reference_occurrences_new50=sum(r["concept_id"] in new_thresholds for r in positions),
                unique_reference_occurrences_all60=len(positions),new_asr_inference=False)


def regression_60(selected,decisions):
    old=prior.load(TEN/"selection.json")["selected"];combined=old+selected
    thresholds={r["concept_id"]:r["selected_auto_threshold"] for r in prior.load(TEN/"threshold_decisions.json")+decisions}
    cases=[
        ("primary allosteronism by this test","primary aldosteronism by this test"),
        ("No primary allosteronism by this test; keep ≥5 mg.","No primary aldosteronism by this test; keep ≥5 mg."),
        ("the 10-year ASCVD risk","the 10-year ASCVD risk"),
        ("secondary hypertension","secondary hypertension"),
        ("systolic blood pressure","systolic blood pressure"),
        ("cardiovascular event","cardiovascular event"),
        ("mineralocorticoid receptors","mineralocorticoid receptors"),
    ]
    rows=[]
    for text,expected in cases:
        result=ctx.candidate(text,combined,thresholds)
        rows.append(dict(input=text,expected=expected,output=result["text"],passed=result["text"]==expected,
                         changes=result["changes"],blocked=result["blocked"]))
    return rows


def preserve():
    baseline=prior.load(HERE/"baseline.json")["files"];strict_count=0;drift=[]
    essential={"app/captions/terminology_normalizer.py","trad_lab/metrics.py"}
    for row in baseline:
        p=Path(row["path"])
        if not p.is_absolute():p=ROOT/p
        actual=prior.sha(p) if p.is_file() else None
        strict=row["path"].startswith(("research/","glossaries/","logs/trad_lab/20261020T074247Z/evaluation/","C:/TRAD-LAB/corpus/")) or row["path"] in essential
        strict_count+=int(strict)
        if actual!=row["sha256"]:
            if strict:raise ValueError("Protected source/evidence changed: "+row["path"])
            drift.append(dict(path=row["path"],before_sha256=row["sha256"],observed_sha256=actual,
                              action="outside_this_task_write_boundary_not_reverted"))
    return dict(files_checked=len(baseline),strictly_protected_files_checked=strict_count,
        original_glossaries_all_prior_research_package_audio_and_asr_unchanged=True,
        other_snapshot_observations=drift,authored_directory=str(HERE),integration_performed=False)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if (HERE/"summary.json").exists():raise SystemExit("Completed experiment exists; no overwrite")
    verify_inputs();selection=prior.load(HERE/"selection.json");selected=selection["selected"]
    raw,cases,excluded=study_cases(selected)
    save("constructed_cases_raw.json",raw);save("constructed_cases.json",cases);save("excluded_duplicates.json",excluded)
    decisions,calibration=calibrate(selected,cases,prior.load(HERE/"protocol.json")["grid"])
    save("threshold_decisions.json",decisions);save("calibration_measurements.json",calibration)
    save("threshold_freeze.json",dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        decisions_sha256=prior.sha(HERE/"threshold_decisions.json"),calibration_only=True))
    print("Fifty threshold decisions frozen before checking",flush=True)
    checked=checking(selected,cases,decisions);save("synthetic_checking.json",checked)
    contexts=context_cases(selected,cases,decisions,calibration);save("context_cases.json",contexts)
    context_results=evaluate_contexts(selected,decisions,contexts);save("context_comparison.json",context_results)
    corpus=comparison_corpus(selected,decisions);save("speech_comparison.json",corpus)
    regressions=regression_60(selected,decisions);save("previous_regressions_combined60.json",regressions)
    table=[]
    concept_categories={c["id"]:c["category"] for c in prior.load(BASE/"integration_candidate/concepts.json")["concepts"]}
    for item,decision in zip(selected,decisions):
        results={}
        for profile in ["raw","previous10_guarded","new50_uniform090_guarded","new50_individualized_unguarded",
                        "new50_individualized_guarded","combined60_individualized_guarded"]:
            obs=[r for r in corpus["occurrences"] if r["concept_id"]==item["concept_id"] and r["profile"]==profile]
            results[profile]=dict(observations=len(obs),exact_reference_form=sum(r["exact_reference_form"] for r in obs))
        table.append(dict(**item,threshold=decision["selected_auto_threshold"],mode=decision["mode"],results=results,
            category=concept_categories[item["concept_id"]],
            operational_approval=False))
    save("term_results.json",table)
    tested=subprocess.run([sys.executable,"-B",str(HERE/"test_50.py")],cwd=ROOT,capture_output=True,text=True,encoding="utf-8")
    save("test_results.json",dict(returncode=tested.returncode,output=tested.stdout+tested.stderr))
    save("preservation.json",preserve())
    summaries=[]
    for profile in ["uniform090_guarded","individualized_unguarded","individualized_guarded"]:
        subset=[r for r in checked if r["profile"]==profile]
        summaries.append(dict(profile=profile,**{key:sum(r[key] for r in subset) for key in
            ["positive_cases","recovered","negative_cases","negative_triggers"]}))
    summary=dict(status="fifty_new_term_trial_complete_not_integrated",selected_terms=50,excluded_original_ten=True,
        random_seed=selection["seed"],pool_size=selection["pool_size"],
        terms_with_fuzzy_candidate=sum(r["selected_auto_threshold"] is not None for r in decisions),
        terms_with_exact_only=sum(r["selected_auto_threshold"] is None for r in decisions),
        threshold_counts=dict(Counter(str(r["selected_auto_threshold"]) for r in decisions)),
        unique_reference_occurrences_new50=corpus["unique_reference_occurrences_new50"],
        unique_reference_occurrences_combined60=corpus["unique_reference_occurrences_all60"],
        synthetic_checking=summaries,context_checking=context_results["summary"],corpus_aggregate=corpus["aggregate"],
        previous_regressions_passed=all(r["passed"] for r in regressions),unit_tests_passed=tested.returncode==0,
        thresholds_retuned_after_checking=False,frozen_guards_changed=False,integration_performed=False,
        independent_clinical_speech_or_live_validation=False)
    save("summary.json",summary);print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
    return tested.returncode


if __name__=="__main__":raise SystemExit(main())
