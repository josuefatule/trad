"""Fixed, more permissive caps; all results are new laboratory artifacts."""
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import json
import re
import subprocess
import sys
import pressure_guard as guard

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
ROOT=BASE.parents[1]
PREVIOUS=BASE/'remaining_terms_trial_37_v1'
sys.path.insert(0,str(PREVIOUS))
import evaluate_remaining as old
from trad_lab.metrics import tokens,metrics,edit_distance
PROFILES=['previous97','direction_guard_same','old_guard_cap090','direction_guard_cap092','direction_guard_cap090','direction_guard_cap088']
CAPS={'direction_guard_cap092':.92,'old_guard_cap090':.90,'direction_guard_cap090':.90,'direction_guard_cap088':.88}


def load(path):return old.load(path)
def sha(path):return old.sha(path)
def save(name,data):
    if Path(name).name!=name:raise ValueError('New trial folder only')
    p=HERE/name
    if p.exists():raise ValueError('Never overwrite evidence: '+name)
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def verify_prior():
    old.verify_prior()
    for r in load(PREVIOUS/'manifest.json')['files']:
        p=PREVIOUS/r['name']
        if p.stat().st_size!=r['bytes'] or sha(p)!=r['sha256']:raise ValueError('Previous experiment changed: '+str(p))


def preserve():
    rows=load(HERE/'baseline.json')['files'];count=0;observations=[]
    for r in rows:
        p=Path(r['path']);p=p if p.is_absolute() else ROOT/p
        actual=sha(p) if p.is_file() else None
        strict=r['path'].startswith(('research/','glossaries/','logs/trad_lab/20261020T074247Z/evaluation/','C:/TRAD-LAB/corpus/')) or r['path'] in ['app/captions/terminology_normalizer.py','trad_lab/metrics.py']
        count+=int(strict)
        if actual!=r['sha256']:
            if strict:raise ValueError('Protected file changed: '+r['path'])
            observations.append(dict(path=r['path'],action='outside_this_task_not_reverted',before=r['sha256'],observed=actual))
    return dict(files_checked=len(rows),strictly_protected_files_checked=count,original_and_prior_evidence_unchanged=True,
        other_workspace_observations=observations,new_directory=str(HERE),integration_performed=False)


def inputs():
    d=load(HERE/'inputs.json')
    return d['selected'],d['profiles'],d['variants']


def candidate(text,profile):
    selected,profiles,variants=INPUTS
    if profile in ['previous97','old_guard_cap090']:
        return guard.previous.candidate(text,selected,profiles[profile],variants,'all_fixes')
    return guard.candidate(text,selected,profiles[profile],variants)


def pressure_cases(selected):
    rows=[]
    def add(text,expected,kind):rows.append(dict(text=text,expected=expected,kind=kind,positive=text!=expected))
    for item in selected:
        canonical=item['canonical_en']
        if 'hyperten' in canonical:opposite=canonical.replace('hyperten','hypoten')
        elif 'hypoten' in canonical:opposite=canonical.replace('hypoten','hyperten')
        else:continue
        for prefix,suffix in [('', ''),('They discussed ',' by this test.'),('No ','; keep ≥5 mg.'),('tag_','')]:
            text=prefix+opposite+suffix;add(text,text,'opposite_direction_no_rewrite')
        for text in [canonical,canonical.upper()]:add(text,text,'already_correct_pressure_term')
    for text in ['primary hypetension','secondary hypetension','resistant hypetension','orthostatic hypetension',
                 'antihypetensive medication','hypetension','hypetensive','hipertension']:
        for prefix,suffix in [('', ''),('They discussed ',' by this test.'),('No ','; keep ≥5 mg.')]:
            probe=prefix+text+suffix;add(probe,probe,'ambiguous_direction_abstain')
    for text,expected in [('primary hypertenson by this test','primary hypertension by this test'),
        ('orthostatic hypotenson by this test','orthostatic hypotension by this test'),
        ('primary hyper tension by this test','primary hypertension by this test'),
        ('No orthostatic hypo tension; keep ≥5 mg.','No orthostatic hypotension; keep ≥5 mg.'),
        ('antihypertension medication','antihypertensive medication'),
        ('primary hypotension; urinary allosterone','primary hypotension; urinary aldosterone'),
        ('tag_primary hypetension; urinary allosterone','tag_primary hypetension; urinary aldosterone')]:
        add(text,expected,'same_direction_or_disjoint_repair')
    for text in ['hypertension and hypotension','hypotension and hypertension','No hypertension; hypotension by this test.',
                 'primary hypo not tension','primary hyper 5 tension','tag_primary hyper tension']:
        add(text,text,'mixed_or_protected_context')
    for i,r in enumerate(rows,1):r['case_id']=f'P{i:04d}'
    return rows


def replay_dataset(name,cases,baseline_rows=None):
    rows=[];summaries=[]
    baseline={r['replay_id']:r for r in baseline_rows} if baseline_rows else {}
    for profile in PROFILES:
        group=[]
        for i,c in enumerate(cases,1):
            if profile=='previous97' and c['case_id'] in baseline:
                previous=baseline[c['case_id']]
                r=dict(text=previous['output'],changes=previous['changes'],blocked=[])
            else:r=candidate(c['text'],profile)
            positive=c['positive'];expected=c['expected']
            passed=(tokens(r['text'])==tokens(expected)) if name=='constructed' and positive else r['text']==expected
            incoming=guard.direction_signature(c['text']);outgoing=guard.direction_signature(r['text'])
            row=dict(profile=profile,case_id=c['case_id'],kind=c.get('kind'),positive=positive,
                input=c['text'],expected=expected,output=r['text'],passed=passed,
                negative_changed=not positive and r['text']!=c['text'],changes=r['changes'],
                direction_sequence_changed=incoming['directions']!=outgoing['directions'],
                direction_guard_blocks=sum('pressure_direction_changed_or_unproven' in b['reasons'] for b in r['blocked']))
            group.append(row)
            if i%400==0:print(f'{name} {profile}: {i}/{len(cases)}',flush=True)
        rows+=group
        summaries.append(dict(profile=profile,cases=len(group),positive_cases=sum(r['positive'] for r in group),
            positive_correct=sum(r['positive'] and r['passed'] for r in group),negative_cases=sum(not r['positive'] for r in group),
            negative_changed=sum(r['negative_changed'] for r in group),passed=sum(r['passed'] for r in group),
            cases_blocked_by_direction_guard=sum(r['direction_guard_blocks']>0 for r in group)))
        print(name+' complete: '+profile,flush=True)
    before={r['case_id']:r for r in rows if r['profile']=='previous97'}
    transitions=[]
    for profile in PROFILES[1:]:
        group=[r for r in rows if r['profile']==profile]
        transitions.append(dict(profile=profile,improved_case_ids=[r['case_id'] for r in group if r['passed'] and not before[r['case_id']]['passed']],
            regressed_case_ids=[r['case_id'] for r in group if not r['passed'] and before[r['case_id']]['passed']],
            newly_changed_negative_ids=[r['case_id'] for r in group if r['negative_changed'] and not before[r['case_id']]['negative_changed']]))
    data=dict(summary=summaries,transitions=transitions,rows=rows)
    save(name+'_comparison.json',data);return data


def speech():
    selected,profiles,variants=INPUTS
    previous=load(PREVIOUS/'speech_comparison.json')
    sources=load(old.prior.CACHED/'inputs/inputs.json');positions=load(PREVIOUS/'reference_occurrences.json')
    rows=[];outputs=[];changes=[];observations=[]
    for model in ['small','medium','large-v3-turbo']:
        for source in sources:
            sid=source['id'];record=load(old.prior.CACHED/'models'/model/sid/'result.json')
            raw,ref=record['hypothesis_raw'],record['reference_raw']
            assert ref==source['reference_raw'] and record['variant']=='baseline'
            for field,digest in [('audio_path','audio_sha256'),('reference_path','reference_sha256')]:assert sha(source[field])==source[digest]
            assert raw==(old.prior.CACHED/'models'/model/sid/'hypothesis.raw.txt').read_text(encoding='utf-8-sig')
            cache={raw:record['metrics']}
            for profile in ['raw']+PROFILES:
                r=dict(text=raw,changes=[],blocked=[],preserved_variants=[],identifier_protections=[],overlap_resolutions=[]) if profile=='raw' else candidate(raw,profile)
                if profile=='previous97':
                    before=next(x for x in previous['outputs'] if x['model']==model and x['sample_id']==sid and x['profile']=='combined97_individualized')
                    assert r['text']==before['candidate_text'],'Baseline no longer reproduces'
                text=r['text']
                if text not in cache:cache[text]=metrics(ref,text)
                m=cache[text];mapped=old.prior.ref_map(tokens(ref),tokens(text),m['word_edits'])
                before_functions=[w for w in guard.previous.first.ctx._tokens(raw) if w in guard.previous.first.ctx.FUNCTION_WORDS]
                after_functions=[w for w in guard.previous.first.ctx._tokens(text) if w in guard.previous.first.ctx.FUNCTION_WORDS]
                source_direction=guard.direction_signature(raw);output_direction=guard.direction_signature(text)
                rows.append(dict(model=model,sample_id=sid,profile=profile,word_errors=m['word_errors'],reference_words=m['reference_words'],wer=m['wer'],
                    character_errors=m['character_errors'],reference_characters=m['reference_characters'],simulated_changes=len(r['changes']),
                    cue_signature_changed=old.prior.cue_signature(raw)!=old.prior.cue_signature(text),
                    function_word_sequence_changed=before_functions!=after_functions,
                    direction_sequence_changed=source_direction['directions']!=output_direction['directions']))
                outputs.append(dict(model=model,sample_id=sid,profile=profile,candidate_text=text,
                    original_hypothesis_sha256=sha(old.prior.CACHED/'models'/model/sid/'hypothesis.raw.txt'),
                    blocked=r['blocked'],preserved_variants=r['preserved_variants'],identifier_protections=r['identifier_protections'],overlap_resolutions=r['overlap_resolutions']))
                changes.extend(dict(model=model,sample_id=sid,profile=profile,**c) for c in r['changes'])
                for p in positions:
                    if p['sample_id']!=sid:continue
                    phrase,_=old.prior.extracted_span(p['ref_left'],p['ref_right'],mapped,tokens(text),m['word_edits'])
                    observations.append(dict(**p,model=model,profile=profile,observed_tokens=phrase,exact_reference_form=phrase==p['reference_tokens']))
            print(f'Cached speech: {model}/{sid}',flush=True)
    aggregate=[]
    for model in ['small','medium','large-v3-turbo']:
        for profile in ['raw']+PROFILES:
            group=[r for r in rows if r['model']==model and r['profile']==profile]
            errors=sum(r['word_errors'] for r in group);words=sum(r['reference_words'] for r in group)
            aggregate.append(dict(model=model,profile=profile,word_errors=errors,reference_words=words,wer=errors/words,
                simulated_changes=sum(r['simulated_changes'] for r in group),samples_with_changed_cues=sum(r['cue_signature_changed'] for r in group),
                samples_with_changed_function_words=sum(r['function_word_sequence_changed'] for r in group),
                samples_with_changed_direction_sequence=sum(r['direction_sequence_changed'] for r in group)))
    data=dict(aggregate=aggregate,rows=rows,outputs=outputs,changes=changes,occurrences=observations,unique_reference_occurrences=len(positions),new_asr_inference=False)
    save('speech_comparison.json',data)
    terms=[]
    for item in selected:
        results={}
        for profile in ['raw']+PROFILES:
            group=[r for r in observations if r['concept_id']==item['concept_id'] and r['profile']==profile]
            results[profile]=dict(observations=len(group),exact_reference_form=sum(r['exact_reference_form'] for r in group))
        terms.append(dict(**item,thresholds={profile:profiles[profile][item['concept_id']] for profile in PROFILES},results=results,operational_approval=False))
    save('term_results.json',terms);return data


def main():
    global INPUTS
    sys.stdout.reconfigure(encoding='utf-8')
    if (HERE/'protocol.json').exists():raise SystemExit('Frozen experiment already exists')
    verify_prior()
    selected=load(old.SIXTY/'selection.json')['selected']+load(PREVIOUS/'selection.json')['selected']
    decisions=load(PREVIOUS/'combined_thresholds.json')['decisions']
    original={r['concept_id']:r['selected_auto_threshold'] for r in decisions}
    variants=load(PREVIOUS/'variant_preservation.json')['forms']
    profiles={p:{cid:None if value is None else min(value,CAPS[p]) if p in CAPS else value for cid,value in original.items()} for p in PROFILES}
    assert len(selected)==97 and sum(v is None for v in original.values())==17
    save('inputs.json',dict(selected=selected,original_decisions=decisions,profiles=profiles,variants=variants,exact_only_terms_stay_exact=True))
    INPUTS=inputs()
    cases=pressure_cases(selected);save('pressure_cases.json',cases)
    constructed=[dict(case_id=c['replay_id'],kind=c['kind'],text=c['text'],expected=c.get('intended',c['text']) if c['positive'] else c['text'],positive=c['positive']) for c in load(PREVIOUS/'combined_checking_cases.json')]
    contexts=[dict(case_id=c['replay_id'],kind=c['kind'],text=c['text'],expected=c['expected'],positive=c['positive']) for c in load(PREVIOUS/'all_context_cases.json')]
    regressions=[dict(case_id=c['case_id'],kind=c['kind'],text=c['text'],expected=c['expected'],positive=c['positive']) for c in load(old.REFINED/'regression_cases.json')]
    save('constructed_cases.json',constructed);save('context_cases.json',contexts);save('existing_regression_cases.json',regressions)
    tests=subprocess.run([sys.executable,'-B',str(HERE/'test_pressure.py')],capture_output=True,text=True,encoding='utf-8',cwd=ROOT)
    save('development_tests.json',dict(returncode=tests.returncode,output=tests.stdout+tests.stderr))
    if tests.returncode:raise SystemExit(tests.stdout+tests.stderr)
    protocol=dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),same_97_terms=True,exact_only_17_unchanged=True,
        thresholds='For each existing active threshold T use min(T, cap). Caps are fixed at .92, .90 and .88 before replay; no ASR-based selection or retuning.',
        pressure_policy='Before selection require unchanged ordered direction signature. Visible hyper/hypo roots and exact split forms are preserved. Near forms without visible direction abstain as ambiguous.',
        profiles=PROFILES,source_hashes=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in [Path(__file__),HERE/'pressure_guard.py',HERE/'test_pressure.py',old.REFINED/'boundary_normalizer.py',old.SIXTY/'lab_normalizer.py',BASE/'context_boundary_trial_10_v1/evaluate_context.py',ROOT/'app/captions/terminology_normalizer.py',ROOT/'trad_lab/metrics.py']],
        frozen_data=[dict(name=name,sha256=sha(HERE/name)) for name in ['inputs.json','pressure_cases.json','constructed_cases.json','context_cases.json','existing_regression_cases.json']],
        prior_failures_used_for_development=True,independent_holdout=False,new_asr_inference=False,write_boundary=str(HERE),integration_performed=False)
    save('protocol.json',protocol);print('Policies, fixed caps and datasets frozen before replay',flush=True)
    baseline_constructed=load(PREVIOUS/'combined_checking.json')['rows']
    baseline_context=[r for r in load(PREVIOUS/'context_comparison.json')['rows'] if r['profile']=='combined97_individualized']
    pressure=replay_dataset('pressure',cases)
    constructed_result=replay_dataset('constructed',constructed,baseline_constructed)
    context_result=replay_dataset('context',contexts,baseline_context)
    regression=replay_dataset('regression',regressions)
    corpus=speech();save('preservation.json',preserve())
    summary=dict(status='flexible_97_replay_complete_not_integrated',same_97_terms=True,active_terms=80,exact_only_terms=17,
        pressure_controls=pressure['summary'],constructed=constructed_result['summary'],contexts=context_result['summary'],regressions=regression['summary'],
        corpus_aggregate=corpus['aggregate'],unit_tests_passed=True,policies_or_caps_retuned_after_checking=False,
        independent_holdout=False,new_asr_inference=False,clinical_adjudication=False,integration_performed=False)
    save('summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
