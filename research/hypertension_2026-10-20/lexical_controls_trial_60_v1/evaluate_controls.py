"""Replay the frozen sixty terms with new laboratory-only lexical policies."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

import lab_normalizer as lab
from trad_lab.metrics import metrics, tokens, edit_distance

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
ROOT=lab.ROOT
TEN=BASE/'tolerance_trial_10_v1'
FIFTY=BASE/'tolerance_trial_50_v1'
GUARD=BASE/'context_boundary_trial_10_v1'
prior=lab.ctx.prior


def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(name,data):
    if Path(name).name!=name:raise ValueError('New trial directory only')
    (HERE/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def verify_prior():
    for directory in [TEN,FIFTY,GUARD,BASE/'integration_candidate',BASE/'laboratory_validation_v1']:
        for r in load(directory/'manifest.json')['files']:
            p=directory/r['name']
            if p.stat().st_size!=r['bytes'] or sha(p)!=r['sha256']:raise ValueError('Old evidence drift: '+str(p))


def preservation():
    strict_count=0;other=[]
    for r in load(HERE/'baseline.json')['files']:
        p=Path(r['path']);p=p if p.is_absolute() else ROOT/p
        actual=sha(p) if p.is_file() else None
        strict=r['path'].startswith(('research/','glossaries/','logs/trad_lab/20261020T074247Z/evaluation/','C:/TRAD-LAB/corpus/')) or r['path'] in ['app/captions/terminology_normalizer.py','trad_lab/metrics.py']
        strict_count+=int(strict)
        if actual!=r['sha256']:
            if strict:raise ValueError('Protected source modified: '+r['path'])
            other.append(dict(path=r['path'],before=r['sha256'],observed=actual,action='outside_task_not_reverted'))
    return dict(files_checked=len(load(HERE/'baseline.json')['files']),strictly_protected_files_checked=strict_count,
        original_and_prior_evidence_unchanged=True,other_workspace_observations=other,
        new_directory=str(HERE),integration_performed=False)


def inputs():
    selected=load(HERE/'selection.json')['selected']
    decisions=load(HERE/'thresholds.json')['decisions']
    thresholds={r['concept_id']:r['selected_auto_threshold'] for r in decisions}
    variants=load(HERE/'variant_preservation.json')['forms']
    return selected,thresholds,variants


def result(text,profile):
    selected,thresholds,variants=INPUTS
    if profile=='old60':return lab.ctx.candidate(text,selected,thresholds)
    return lab.candidate(text,selected,thresholds,variants,profile)


def build_regressions(selected,variants):
    rows=[]
    def add(text,expected,kind,cid=None):
        rows.append(dict(text=text,expected=expected,kind=kind,concept_id=cid,positive=text!=expected))
    for r in variants:
        for prefix,suffix in [('', ''),('They discussed ',' by this test.'),('No evidence of ','; keep ≥5 mg.')]:
            text=prefix+r['form']+suffix;add(text,text,'registered_variant_preservation',r['concept_id'])
    pairs=[('pressure','pressures'),('risk','risks'),('target','targets'),('event','events'),
        ('receptor','receptors'),('inhibitor','inhibitors'),('adult','adults'),('agent','agents'),
        ('contraceptive','contraceptives'),('salt','salts'),('antagonist','antagonists'),
        ('diet','diets'),('review','reviews'),('therapy','therapies'),('disease','diseases'),
        ('co-chair','co-chairs'),('activity','activities'),('meta-analysis','meta-analyses')]
    for r in selected:
        text=r['canonical_en']
        for a,b in pairs:
            for source,target in [(a,b),(b,a)]:
                replaced,n=re.subn(r'\b'+re.escape(source)+r'$',target,text)
                if n:
                    for prefix,suffix in [('', ''),('They discussed ',' by this test.'),('No evidence of ','; keep ≥5 mg.')]:
                        probe=prefix+replaced+suffix;add(probe,probe,'singular_plural_preservation',r['concept_id'])
    for r in load(FIFTY/'overlap_diagnostics.json'):
        add(r['input'],r['expected'],'known_overlap_repair',r['concept_id'])
    for r in load(FIFTY/'previous_regressions_combined60.json'):
        add(r['input'],r['expected'],'previous_regression')
    for text in ['tag_pharmacologic therapy','tag_elvated blood pressure','nonelevated blood pressure',
        'cardiovascular not risk','diastolic by blood pressure','primary allosteronism by not 5 mg',
        'diastolic bloood pressures','cardiovascular riks by patients']:
        # The last case is a recoverable typo and explicitly expects its repair.
        expected='cardiovascular risk by patients' if text=='cardiovascular riks by patients' else (
            'primary aldosteronism by not 5 mg' if text=='primary allosteronism by not 5 mg' else text)
        add(text,expected,'additional_boundary_or_context')
    for i,r in enumerate(rows,1):r['case_id']=f'R{i:04d}'
    return rows


def replay_constructed():
    cases=[]
    excluded=set(load(TEN/'checking_overlap_audit.json')['exact_duplicate_checking_case_ids'])
    for folder,prefix in [(TEN,'ten'),(FIFTY,'fifty')]:
        for r in load(folder/'constructed_cases.json'):
            if r['split']=='synthetic_checking' and (folder!=TEN or r['case_id'] not in excluded):
                cases.append(dict(**r,source_group=prefix,original_case_id=r['case_id'],
                    replay_id=prefix+':'+r['case_id']))
    save('constructed_checking_cases.json',cases)
    rows=[]
    for profile in ['old60','all_fixes']:
        for i,c in enumerate(cases,1):
            r=result(c['text'],profile)
            expected=c.get('intended',c['text']) if c['positive'] else c['text']
            rows.append(dict(replay_id=c['replay_id'],concept_id=c['concept_id'],profile=profile,
                positive=c['positive'],output=r['text'],expected=expected,
                positive_correct=c['positive'] and tokens(r['text'])==tokens(expected),
                negative_changed=not c['positive'] and r['text']!=c['text'],changes=r['changes'],
                blocked_reasons=dict(Counter(reason for b in r['blocked'] for reason in b['reasons']))))
            if i%300==0:print(f'Constructed replay {profile}: {i}/{len(cases)}',flush=True)
    summary=[]
    for profile in ['old60','all_fixes']:
        group=[r for r in rows if r['profile']==profile]
        summary.append(dict(profile=profile,positive_cases=sum(r['positive'] for r in group),
            positive_correct=sum(r['positive_correct'] for r in group),negative_cases=sum(not r['positive'] for r in group),
            negative_changed=sum(r['negative_changed'] for r in group)))
    data=dict(summary=summary,rows=rows,scope='All sixty terms active together; old synthetic recipes previously explored; no calibration')
    save('constructed_comparison.json',data);return data


def replay_contexts():
    cases=[]
    for folder,prefix in [(GUARD,'ten'),(FIFTY,'fifty')]:
        for r in load(folder/'context_cases.json'):
            cases.append(dict(**r,source_group=prefix,replay_id=prefix+':'+r['case_id']))
    save('context_cases.json',cases)
    rows=[]
    for profile in ['old60','all_fixes']:
        for c in cases:
            r=result(c['text'],profile)
            rows.append(dict(replay_id=c['replay_id'],concept_id=c['concept_id'],profile=profile,
                positive=c['positive'],input=c['text'],expected=c['expected'],output=r['text'],
                passed=r['text']==c['expected'],negative_changed=not c['positive'] and r['text']!=c['text'],
                changes=r['changes'],overlap_resolutions=r.get('overlap_resolutions',[])))
        print('Context replay complete: '+profile,flush=True)
    summary=[]
    for profile in ['old60','all_fixes']:
        group=[r for r in rows if r['profile']==profile]
        summary.append(dict(profile=profile,positive_cases=sum(r['positive'] for r in group),
            positive_correct=sum(r['passed'] and r['positive'] for r in group),
            negative_cases=sum(not r['positive'] for r in group),negative_changed=sum(r['negative_changed'] for r in group)))
    before={r['replay_id']:r for r in rows if r['profile']=='old60'}
    improvements=[r['replay_id'] for r in rows if r['profile']=='all_fixes' and r['passed'] and not before[r['replay_id']]['passed']]
    regressions=[r['replay_id'] for r in rows if r['profile']=='all_fixes' and not r['passed'] and before[r['replay_id']]['passed']]
    data=dict(summary=summary,improved_cases=improvements,regressed_cases=regressions,rows=rows)
    save('context_comparison.json',data);return data


def replay_regressions(cases):
    rows=[]
    for profile in ['old60','variants_only','variants_and_number','all_fixes']:
        for c in cases:
            r=result(c['text'],profile)
            rows.append(dict(**c,profile=profile,output=r['text'],passed=r['text']==c['expected'],
                changes=r['changes'],preserved_variants=r.get('preserved_variants',[]),overlap_resolutions=r.get('overlap_resolutions',[])))
    summary=[dict(profile=p,cases=sum(r['profile']==p for r in rows),passed=sum(r['profile']==p and r['passed'] for r in rows))
             for p in ['old60','variants_only','variants_and_number','all_fixes']]
    data=dict(summary=summary,rows=rows,scope='Known defects plus predeclared laboratory probes; not independent clinical validation')
    save('regression_comparison.json',data);return data


def speech():
    previous=load(FIFTY/'speech_comparison.json')
    sources=load(prior.CACHED/'inputs/inputs.json')
    positions=load(FIFTY/'reference_occurrences.json')
    outputs=[];rows=[];changes=[];observations=[]
    selected_ids={r['concept_id'] for r in INPUTS[0]}
    assert {r['concept_id'] for r in positions}==selected_ids
    for model in ['small','medium','large-v3-turbo']:
        for source in sources:
            sid=source['id'];record=load(prior.CACHED/'models'/model/sid/'result.json')
            raw,ref=record['hypothesis_raw'],record['reference_raw']
            assert ref==source['reference_raw']
            for field,hashfield in [('audio_path','audio_sha256'),('reference_path','reference_sha256')]:
                assert sha(source[field])==source[hashfield]
            metric_cache={raw:record['metrics']}
            for profile in ['raw','previous10','old60','variants_only','variants_and_number','all_fixes']:
                if profile=='raw':r=dict(text=raw,changes=[],blocked=[])
                elif profile=='previous10':
                    old=next(x for x in previous['outputs'] if x['model']==model and x['sample_id']==sid and x['profile']=='previous10_guarded')
                    r=dict(text=old['candidate_text'],changes=[],blocked=[])
                else:r=result(raw,profile)
                if profile=='old60':
                    expected=next(x for x in previous['outputs'] if x['model']==model and x['sample_id']==sid and x['profile']=='combined60_individualized_guarded')
                    assert r['text']==expected['candidate_text'],'Old sixty baseline did not reproduce'
                text=r['text']
                if text not in metric_cache:metric_cache[text]=metrics(ref,text)
                m=metric_cache[text]
                cue_changed=prior.cue_signature(raw)!=prior.cue_signature(text)
                function_changed=[w for w in lab.ctx._tokens(raw) if w in lab.ctx.FUNCTION_WORDS]!=[w for w in lab.ctx._tokens(text) if w in lab.ctx.FUNCTION_WORDS]
                rows.append(dict(model=model,sample_id=sid,profile=profile,word_errors=m['word_errors'],reference_words=m['reference_words'],wer=m['wer'],
                    character_errors=m['character_errors'],reference_characters=m['reference_characters'],
                    cue_signature_changed=cue_changed,function_word_sequence_changed=function_changed,simulated_changes=len(r['changes'])))
                outputs.append(dict(model=model,sample_id=sid,profile=profile,candidate_text=text,
                    original_raw_sha256=sha(prior.CACHED/'models'/model/sid/'hypothesis.raw.txt'),
                    preserved_variants=r.get('preserved_variants',[]),blocked=r['blocked'],overlap_resolutions=r.get('overlap_resolutions',[])))
                changes.extend(dict(model=model,sample_id=sid,profile=profile,**c) for c in r['changes'])
                mapped=prior.ref_map(tokens(ref),tokens(text),m['word_edits'])
                for p in positions:
                    if p['sample_id']!=sid:continue
                    phrase,_=prior.extracted_span(p['ref_left'],p['ref_right'],mapped,tokens(text),m['word_edits'])
                    observations.append(dict(**p,model=model,profile=profile,observed_tokens=phrase,exact_reference_form=phrase==p['reference_tokens']))
            print(f'Cached speech complete: {model}/{sid}',flush=True)
    aggregate=[]
    for model in ['small','medium','large-v3-turbo']:
        for profile in ['raw','previous10','old60','variants_only','variants_and_number','all_fixes']:
            group=[r for r in rows if r['model']==model and r['profile']==profile]
            errors=sum(r['word_errors'] for r in group);words=sum(r['reference_words'] for r in group)
            aggregate.append(dict(model=model,profile=profile,word_errors=errors,reference_words=words,wer=errors/words,
                simulated_changes=sum(r['simulated_changes'] for r in group),
                samples_with_changed_cues=sum(r['cue_signature_changed'] for r in group),
                samples_with_changed_function_words=sum(r['function_word_sequence_changed'] for r in group)))
    data=dict(aggregate=aggregate,rows=rows,outputs=outputs,changes=changes,occurrences=observations,
        unique_reference_occurrences=len(positions),new_asr_inference=False)
    save('speech_comparison.json',data)
    term_table=[]
    for item in INPUTS[0]:
        by_profile={}
        for profile in ['raw','previous10','old60','variants_only','variants_and_number','all_fixes']:
            group=[r for r in observations if r['concept_id']==item['concept_id'] and r['profile']==profile]
            by_profile[profile]=dict(observations=len(group),exact_reference_form=sum(r['exact_reference_form'] for r in group))
        term_table.append(dict(**item,frozen_threshold=INPUTS[1][item['concept_id']],results=by_profile,operational_approval=False))
    save('term_results.json',term_table)
    audited=[]
    for c in changes:
        if c['profile']!='all_fixes':continue
        record=load(prior.CACHED/'models'/c['model']/c['sample_id']/'result.json')
        raw,ref=record['hypothesis_raw'],record['reference_raw']
        assert raw[c['start']:c['end']]==c['source']
        once=raw[:c['start']]+c['replacement']+raw[c['end']:]
        delta=edit_distance(tokens(ref),tokens(once))-record['metrics']['word_errors']
        audited.append(dict(**c,word_error_delta_if_applied_alone=delta,
            assessment='improved' if delta<0 else 'worsened' if delta>0 else 'neutral',
            independent_clinical_adjudication=False))
    save('correction_review.json',audited)
    return data


def main():
    global INPUTS
    sys.stdout.reconfigure(encoding='utf-8')
    if (HERE/'protocol.json').exists():raise SystemExit('Frozen trial exists; do not overwrite')
    verify_prior()
    selected=load(TEN/'selection.json')['selected']+load(FIFTY/'selection.json')['selected']
    decisions=load(TEN/'threshold_decisions.json')+load(FIFTY/'threshold_decisions.json')
    assert len(selected)==len({r['concept_id'] for r in selected})==60
    assert {r['concept_id'] for r in decisions}=={r['concept_id'] for r in selected}
    variants=[r for r in load(BASE/'integration_candidate/form_decisions.json')['forms']
              if r['concept_id'] in {s['concept_id'] for s in selected} and r['language']=='en' and r['bucket']=='reviewable_variant']
    save('selection.json',dict(selected=selected,new_sampling=False,same_sixty_in_original_order=True))
    save('thresholds.json',dict(decisions=decisions,recalibration_performed=False,original_thresholds_unchanged=True))
    save('variant_preservation.json',dict(forms=variants,policy='Preserve spans verbatim only; never expand or substitute; no equivalence approval',original_package_changed=False))
    INPUTS=inputs()
    regression_cases=build_regressions(selected,variants);save('regression_cases.json',regression_cases)
    tested=subprocess.run([sys.executable,'-B',str(HERE/'test_controls.py')],capture_output=True,text=True,encoding='utf-8',cwd=ROOT)
    save('development_test_results.json',dict(returncode=tested.returncode,output=tested.stdout+tested.stderr))
    if tested.returncode:raise SystemExit(tested.stdout+tested.stderr)
    protocol=dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),same_sixty=True,same_thresholds=True,
        prior_failures_used_to_design_rules=True,independent_holdout=False,
        selection_sha256=sha(HERE/'selection.json'),thresholds_sha256=sha(HERE/'thresholds.json'),
        sources=[dict(name=name,sha256=sha(HERE/name)) for name in ['lab_normalizer.py','evaluate_controls.py','test_controls.py','variant_preservation.json','regression_cases.json']],
        variants='Preserve registered English reviewable_variant spans verbatim; this does not approve equivalence or substitution.',
        plurals='Reject regular and declared irregular number changes in either direction before candidate selection; no inflected replacement generation.',
        overlaps='Promote a guarded automatic phrase only over fully contained exact proper subphrases also contained in its canonical token sequence; preserve all other exact conflicts.',
        profiles=['old60','variants_only','variants_and_number','all_fixes'],
        write_boundary=str(HERE),new_asr_inference=False,integration_performed=False)
    save('protocol.json',protocol)
    print('Policies and thresholds frozen before replay',flush=True)
    constructed=replay_constructed();contexts=replay_contexts();regressions=replay_regressions(regression_cases);corpus=speech()
    save('preservation.json',preservation())
    summary=dict(status='laboratory_replay_complete_not_integrated',same_sixty=True,thresholds_unchanged=True,
        variant_preservation_records=len(variants),corpus_aggregate=corpus['aggregate'],
        constructed=constructed['summary'],contexts=contexts['summary'],
        context_improvements=len(contexts['improved_cases']),context_regressions=len(contexts['regressed_cases']),
        regression_summary=regressions['summary'],development_tests_passed=True,
        policies_retuned_after_replay=False,new_asr_inference=False,independent_clinical_validation=False,integration_performed=False)
    save('summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
