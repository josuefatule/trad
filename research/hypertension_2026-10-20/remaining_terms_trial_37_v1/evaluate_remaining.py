"""Remaining 37 reference-covered terms, unchanged corrected laboratory rules."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import random
import re
import sys

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
ROOT=BASE.parents[1]
SIXTY=BASE/'lexical_controls_trial_60_v1'
REFINED=SIXTY/'boundary_refinement_v2'
FIFTY=BASE/'tolerance_trial_50_v1'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(REFINED));sys.path.insert(0,str(FIFTY))
import boundary_normalizer as corrected
import evaluate_50 as fifty
from trad_lab.metrics import tokens,metrics,edit_distance
prior=corrected.first.ctx.prior
GRID=[.86,.88,.90,.92,.94,.96,.98,.99,1.00]
SEED=int.from_bytes(hashlib.sha256(b'TRAD remaining37 corrected trial v1').digest()[:8],'big')


def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return prior.sha(path)
def save(name,data):
    if Path(name).name!=name:raise ValueError('New research directory only')
    path=HERE/name
    if path.exists():raise ValueError('Never overwrite research output: '+name)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def verify_prior():
    for directory in [BASE/'tolerance_trial_10_v1',FIFTY,BASE/'context_boundary_trial_10_v1',
                      SIXTY,REFINED,BASE/'integration_candidate',BASE/'laboratory_validation_v1']:
        for row in load(directory/'manifest.json')['files']:
            p=directory/row['name']
            if p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256']:raise ValueError('Prior evidence changed: '+str(p))


def preservation():
    rows=load(HERE/'baseline.json')['files'];strict_count=0;other=[]
    for r in rows:
        p=Path(r['path']);p=p if p.is_absolute() else ROOT/p
        actual=sha(p) if p.is_file() else None
        strict=r['path'].startswith(('research/','glossaries/','logs/trad_lab/20261020T074247Z/evaluation/','C:/TRAD-LAB/corpus/')) or r['path'] in ['app/captions/terminology_normalizer.py','trad_lab/metrics.py']
        strict_count+=int(strict)
        if actual!=r['sha256']:
            if strict:raise ValueError('Protected source/evidence changed: '+r['path'])
            other.append(dict(path=r['path'],before=r['sha256'],observed=actual,action='outside_this_task_not_reverted'))
    return dict(files_checked=len(rows),strictly_protected_files_checked=strict_count,
        original_and_prior_evidence_unchanged=True,other_workspace_observations=other,
        new_directory=str(HERE),integration_performed=False)


def candidate(text,selected,thresholds,variants):
    return corrected.candidate(text,selected,thresholds,variants,'all_fixes')


def study_cases(selected,forms):
    raw,_,_=fifty.study_cases(selected)
    for item in selected:
        name=item['canonical_en'];cid=item['concept_id']
        contrasts=[(f['form'],'preserve_registered_variant') for f in forms if f['concept_id']==cid]
        # Predeclared number contrasts on common countable heads only.
        pairs=[('pressure','pressures'),('function','functions'),('implication','implications'),
            ('blocker','blockers'),('antidepressant','antidepressants'),('medication','medications'),
            ('adult','adults'),('diet','diets'),('therapy','therapies'),('disease','diseases'),
            ('millimeter','millimeters'),('milligram','milligrams')]
        for a,b in pairs:
            for source,target in [(a,b),(b,a)]:
                text,n=re.subn(r'\b'+source+r'\b',target,name)
                if n:contrasts.append((text,'preserve_grammatical_number'))
        for text,kind in contrasts:
            if text==name:continue
            for split in ['calibration','synthetic_checking']:
                raw.append(dict(concept_id=cid,split=split,kind=kind,positive=False,
                    text=text if split=='calibration' else 'They discussed '+text+' by this test.',
                    origin='Preservation contrast; no new equivalence approval'))
    for i,r in enumerate(raw,1):r['case_id']=f'R{i:05d}'
    seen={};effective=[];excluded=[]
    for split in ['calibration','synthetic_checking']:
        for r in raw:
            if r['split']!=split:continue
            key=(r['concept_id'],r['positive'],r['text'])
            if key in seen:excluded.append(dict(case_id=r['case_id'],duplicate_of=seen[key],split=split))
            else:seen[key]=r['case_id'];effective.append(r)
    return raw,effective,excluded


def case_result(case,item,threshold,variants):
    r=candidate(case['text'],[item],{item['concept_id']:threshold},variants)
    return dict(case_id=case['case_id'],threshold=threshold,
        recovered=case['positive'] and tokens(r['text'])==tokens(case['intended']),
        triggered=any(c['rule']=='glossary_fuzzy' for c in r['changes']),
        negative_changed=not case['positive'] and r['text']!=case['text'],
        output=r['text'],changes=r['changes'],
        guard_rejection_reasons=dict(Counter(reason for b in r['blocked'] for reason in b['reasons'])))


def calibrate(selected,cases,variants):
    decisions=[];measurements=[]
    for i,item in enumerate(selected,1):
        subset=[r for r in cases if r['concept_id']==item['concept_id'] and r['split']=='calibration']
        scores=[]
        for threshold in GRID:
            rows=[case_result(c,item,threshold,variants) for c in subset];measurements+=rows
            scores.append(dict(threshold=threshold,**prior.score_cases(rows,subset)))
        eligible=[s for s in scores if s['negative_triggers']==0]
        best=max(eligible,key=lambda s:(s['recovered'],s['threshold'])) if eligible else None
        useful=best is not None and best['recovered']>0
        decisions.append(dict(concept_id=item['concept_id'],canonical_en=item['canonical_en'],preferred_es=item['preferred_es'],
            selected_auto_threshold=best['threshold'] if useful else None,
            mode='guarded_fuzzy_candidate' if useful else 'exact_only_no_useful_guarded_fuzzy_recovery',
            calibration_grid=scores,operational_approval=False,
            selection_rule='Highest constructed recovery with zero negative fuzzy triggers; higher threshold breaks ties; zero useful recovery means exact-only',
            corrected_rules_unchanged=True,selected_before_checking=True))
        if i%5==0 or i==len(selected):print(f'Corrected-rule calibration: {i}/{len(selected)}',flush=True)
    return decisions,measurements


def check_isolated(selected,cases,decisions,variants):
    thresholds={r['concept_id']:r['selected_auto_threshold'] for r in decisions};rows=[]
    for item in selected:
        subset=[r for r in cases if r['concept_id']==item['concept_id'] and r['split']=='synthetic_checking']
        for profile,threshold in [('uniform090',.90),('individualized',thresholds[item['concept_id']])]:
            measured=[case_result(c,item,threshold,variants) for c in subset]
            rows.append(dict(concept_id=item['concept_id'],profile=profile,threshold=threshold,
                **prior.score_cases(measured,subset),negative_changed=sum(r['negative_changed'] for r in measured),rows=measured))
    summary=[]
    for profile in ['uniform090','individualized']:
        group=[r for r in rows if r['profile']==profile]
        summary.append(dict(profile=profile,**{k:sum(r[k] for r in group) for k in ['positive_cases','recovered','negative_cases','negative_triggers','negative_changed']}))
    data=dict(summary=summary,rows=rows);save('isolated_checking.json',data);return data


def contextual_replay(selected,decisions,cases,calibration,combined,combined_thresholds,all_variants):
    new_cases=fifty.context_cases(selected,cases,decisions,calibration)
    for c in new_cases:c['replay_id']='new37:'+c['case_id']
    previous=load(REFINED/'context_cases.json')
    save('new_context_cases.json',new_cases)
    all_cases=previous+new_cases;save('all_context_cases.json',all_cases)
    rows=[]
    for profile,terms,thresholds,variants,group in [
        ('new37_uniform090',selected,{r['concept_id']:.90 for r in selected},[f for f in all_variants if f['concept_id'] in {s['concept_id'] for s in selected}],new_cases),
        ('new37_individualized',selected,{r['concept_id']:r['selected_auto_threshold'] for r in decisions},[f for f in all_variants if f['concept_id'] in {s['concept_id'] for s in selected}],new_cases),
        ('combined97_individualized',combined,combined_thresholds,all_variants,all_cases)]:
        for c in group:
            r=candidate(c['text'],terms,thresholds,variants)
            rows.append(dict(profile=profile,replay_id=c['replay_id'],concept_id=c['concept_id'],
                group='new37' if c['replay_id'].startswith('new37:') else 'previous60',
                positive=c['positive'],input=c['text'],expected=c['expected'],output=r['text'],
                passed=r['text']==c['expected'],negative_changed=not c['positive'] and r['text']!=c['text'],
                changes=r['changes'],overlap_resolutions=r['overlap_resolutions'],identifier_protections=r['identifier_protections']))
        print('Context comparison: '+profile,flush=True)
    before={r['replay_id']:r for r in load(REFINED/'context_comparison.json')['rows'] if r['profile']=='all_fixes'}
    regressions=[r for r in rows if r['profile']=='combined97_individualized' and r['group']=='previous60' and before[r['replay_id']]['passed'] and not r['passed']]
    improvements=[r['replay_id'] for r in rows if r['profile']=='combined97_individualized' and r['group']=='previous60' and not before[r['replay_id']]['passed'] and r['passed']]
    summary=[]
    for profile,group in [('new37_uniform090','new37'),('new37_individualized','new37'),('combined97_individualized','new37'),('combined97_individualized','previous60')]:
        subset=[r for r in rows if r['profile']==profile and r['group']==group]
        summary.append(dict(profile=profile,group=group,positive_cases=sum(r['positive'] for r in subset),positive_correct=sum(r['positive'] and r['passed'] for r in subset),
            negative_cases=sum(not r['positive'] for r in subset),negative_changed=sum(r['negative_changed'] for r in subset)))
    data=dict(summary=summary,previous60_regressions=regressions,previous60_improvements=improvements,rows=rows)
    save('context_comparison.json',data);return data


def constructed_combined(cases,combined,thresholds,variants):
    previous=load(REFINED/'constructed_checking_cases.json')
    new=[dict(**r,replay_id='new37:'+r['case_id']) for r in cases if r['split']=='synthetic_checking']
    all_cases=previous+new;save('combined_checking_cases.json',all_cases)
    rows=[]
    for i,c in enumerate(all_cases,1):
        r=candidate(c['text'],combined,thresholds,variants)
        positive=c['positive'];expected=c.get('intended',c['text']) if positive else c['text']
        rows.append(dict(replay_id=c['replay_id'],concept_id=c['concept_id'],group='new37' if c['replay_id'].startswith('new37:') else 'previous60',
            positive=positive,output=r['text'],expected=expected,positive_correct=positive and tokens(r['text'])==tokens(expected),
            negative_changed=not positive and r['text']!=c['text'],changes=r['changes']))
        if i%300==0:print(f'All-97 constructed checking: {i}/{len(all_cases)}',flush=True)
    summary=[]
    for group in ['previous60','new37']:
        subset=[r for r in rows if r['group']==group]
        summary.append(dict(group=group,positive_cases=sum(r['positive'] for r in subset),positive_correct=sum(r['positive_correct'] for r in subset),
            negative_cases=sum(not r['positive'] for r in subset),negative_changed=sum(r['negative_changed'] for r in subset)))
    before={r['replay_id']:r for r in load(REFINED/'constructed_comparison.json')['rows'] if r['profile']=='all_fixes'}
    regression_ids=[r['replay_id'] for r in rows if r['group']=='previous60' and (before[r['replay_id']]['positive_correct'] and not r['positive_correct'] or
        not r['positive'] and not before[r['replay_id']]['negative_changed'] and r['negative_changed'])]
    data=dict(summary=summary,previous60_regression_ids=regression_ids,rows=rows)
    save('combined_checking.json',data);return data


def regressions(combined,thresholds,variants):
    cases=load(REFINED/'regression_cases.json')
    rows=[]
    for c in cases:
        r=candidate(c['text'],combined,thresholds,variants)
        rows.append(dict(**c,output=r['text'],passed=r['text']==c['expected'],changes=r['changes']))
    data=dict(cases=len(rows),passed=sum(r['passed'] for r in rows),rows=rows)
    save('previous_regressions_combined97.json',data);return data


def speech(selected,decisions,combined,thresholds,variants):
    sources=load(prior.CACHED/'inputs/inputs.json');positions=prior.occurrences(combined,sources)
    save('reference_occurrences.json',positions)
    new_ids={r['concept_id'] for r in selected};new_variants=[f for f in variants if f['concept_id'] in new_ids]
    previous=load(REFINED/'speech_comparison.json');outputs=[];rows=[];changes=[];observations=[]
    old=load(SIXTY/'selection.json')['selected'];old_thresholds={r['concept_id']:r['selected_auto_threshold'] for r in load(SIXTY/'thresholds.json')['decisions']}
    old_variants=load(SIXTY/'variant_preservation.json')['forms']
    profiles=['raw','previous60_corrected','new37_uniform090','new37_individualized','combined97_uniform_new37','combined97_individualized']
    for model in ['small','medium','large-v3-turbo']:
        for source in sources:
            sid=source['id'];record=load(prior.CACHED/'models'/model/sid/'result.json')
            raw,ref=record['hypothesis_raw'],record['reference_raw']
            assert ref==source['reference_raw'] and record['variant']=='baseline'
            assert raw==(prior.CACHED/'models'/model/sid/'hypothesis.raw.txt').read_text(encoding='utf-8-sig')
            for field,expected in [('audio_path','audio_sha256'),('reference_path','reference_sha256')]:assert sha(source[field])==source[expected]
            cache={raw:record['metrics']}
            for profile in profiles:
                if profile=='raw':r=dict(text=raw,changes=[],blocked=[],preserved_variants=[],overlap_resolutions=[],identifier_protections=[])
                elif profile=='previous60_corrected':
                    r=candidate(raw,old,old_thresholds,old_variants)
                    previous_output=next(x for x in previous['outputs'] if x['model']==model and x['sample_id']==sid and x['profile']=='all_fixes')
                    assert r['text']==previous_output['candidate_text'],'Previous sixty output did not reproduce'
                else:
                    terms=combined if profile.startswith('combined') else selected
                    use_variants=variants if profile.startswith('combined') else new_variants
                    use_thresholds=dict(thresholds) if profile.startswith('combined') else {r['concept_id']:r['selected_auto_threshold'] for r in decisions}
                    if 'uniform' in profile:use_thresholds.update({cid:.90 for cid in new_ids})
                    r=candidate(raw,terms,use_thresholds,use_variants)
                text=r['text']
                if text not in cache:cache[text]=metrics(ref,text)
                m=cache[text];mapped=prior.ref_map(tokens(ref),tokens(text),m['word_edits'])
                function_changed=[w for w in corrected.first.ctx._tokens(raw) if w in corrected.first.ctx.FUNCTION_WORDS]!=[w for w in corrected.first.ctx._tokens(text) if w in corrected.first.ctx.FUNCTION_WORDS]
                rows.append(dict(model=model,sample_id=sid,profile=profile,word_errors=m['word_errors'],reference_words=m['reference_words'],wer=m['wer'],
                    character_errors=m['character_errors'],reference_characters=m['reference_characters'],
                    cue_signature_changed=prior.cue_signature(raw)!=prior.cue_signature(text),function_word_sequence_changed=function_changed,
                    simulated_changes=len(r['changes'])))
                outputs.append(dict(model=model,sample_id=sid,profile=profile,candidate_text=text,original_hypothesis_sha256=sha(prior.CACHED/'models'/model/sid/'hypothesis.raw.txt'),
                    preserved_variants=r['preserved_variants'],blocked=r['blocked'],overlap_resolutions=r['overlap_resolutions'],identifier_protections=r['identifier_protections']))
                changes.extend(dict(model=model,sample_id=sid,profile=profile,**c) for c in r['changes'])
                for p in positions:
                    if p['sample_id']!=sid:continue
                    phrase,_=prior.extracted_span(p['ref_left'],p['ref_right'],mapped,tokens(text),m['word_edits'])
                    observations.append(dict(**p,model=model,profile=profile,observed_tokens=phrase,exact_reference_form=phrase==p['reference_tokens'],group='new37' if p['concept_id'] in new_ids else 'previous60'))
            print(f'Cached speech comparison: {model}/{sid}',flush=True)
    aggregate=[]
    for model in ['small','medium','large-v3-turbo']:
        for profile in profiles:
            group=[r for r in rows if r['model']==model and r['profile']==profile]
            errors=sum(r['word_errors'] for r in group);words=sum(r['reference_words'] for r in group)
            aggregate.append(dict(model=model,profile=profile,word_errors=errors,reference_words=words,wer=errors/words,
                simulated_changes=sum(r['simulated_changes'] for r in group),samples_with_changed_cues=sum(r['cue_signature_changed'] for r in group),
                samples_with_changed_function_words=sum(r['function_word_sequence_changed'] for r in group)))
    data=dict(aggregate=aggregate,rows=rows,outputs=outputs,changes=changes,occurrences=observations,
        unique_reference_occurrences_new37=sum(p['concept_id'] in new_ids for p in positions),unique_reference_occurrences_all97=len(positions),new_asr_inference=False)
    save('speech_comparison.json',data)
    table=[]
    for item in combined:
        results={}
        for profile in profiles:
            group=[r for r in observations if r['concept_id']==item['concept_id'] and r['profile']==profile]
            results[profile]=dict(observations=len(group),exact_reference_form=sum(r['exact_reference_form'] for r in group))
        table.append(dict(**item,group='new37' if item['concept_id'] in new_ids else 'previous60',threshold=thresholds[item['concept_id']],results=results,operational_approval=False))
    save('term_results.json',table)
    return data


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if (HERE/'protocol.json').exists():raise SystemExit('Frozen experiment exists; do not overwrite')
    verify_prior()
    old=load(SIXTY/'selection.json')['selected'];old_ids={r['concept_id'] for r in old}
    pool=load(FIFTY/'selection.json')['pool'];selected=sorted([r for r in pool if r['concept_id'] not in old_ids],key=lambda r:r['concept_id'])
    random.Random(SEED).shuffle(selected)
    assert len(selected)==37 and len({r['concept_id'] for r in old+selected})==97
    all_ids={r['concept_id'] for r in old+selected}
    forms=[f for f in load(BASE/'integration_candidate/form_decisions.json')['forms'] if f['concept_id'] in all_ids and f['language']=='en' and f['bucket']=='reviewable_variant']
    new_forms=[f for f in forms if f['concept_id'] not in old_ids]
    save('selection.json',dict(seed=SEED,selection_rule='Complete remaining set of the original 97 reference-covered concepts; seeded random order only, no fresh subsampling or reroll',
        user_confirmed_scope='37 remaining concepts with audio, not the other 597 glossary concepts',selected=selected,excluded_previous60_ids=sorted(old_ids),combined_count=97))
    save('variant_preservation.json',dict(forms=forms,new37_forms=new_forms,policy='Preserve registered research variants verbatim; never substitute or approve semantic equivalence'))
    raw,cases,excluded=study_cases(selected,new_forms)
    save('constructed_cases_raw.json',raw);save('constructed_cases.json',cases);save('excluded_duplicates.json',excluded)
    protocol=dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),scope='Remaining 37 reference-covered concepts',
        corrected_rules_unchanged=True,grid=GRID,previous60_thresholds_unchanged=True,
        calibration='New terms only, corrected rules, per-term constructed calibration. Max recovery with zero negative fuzzy triggers; tie to higher threshold. No useful recovery means exact-only.',
        checking='Exact duplicates excluded across constructed splits before calibration; freeze decisions before cached speech and combined checking. No retuning.',
        source_hashes=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in [Path(__file__),REFINED/'boundary_normalizer.py',SIXTY/'lab_normalizer.py',BASE/'context_boundary_trial_10_v1/evaluate_context.py',FIFTY/'evaluate_50.py',BASE/'tolerance_trial_10_v1/evaluate_trial.py',ROOT/'app/captions/terminology_normalizer.py',ROOT/'trad_lab/metrics.py']],
        selection_sha256=sha(HERE/'selection.json'),variants_sha256=sha(HERE/'variant_preservation.json'),
        independent_holdout=False,previously_explored_audio=True,new_asr_inference=False,integration_performed=False,write_boundary=str(HERE))
    save('protocol.json',protocol)
    decisions,calibration=calibrate(selected,cases,new_forms)
    save('threshold_decisions.json',decisions);save('calibration_measurements.json',calibration)
    old_decisions=load(SIXTY/'thresholds.json')['decisions']
    combined=old+selected;thresholds={r['concept_id']:r['selected_auto_threshold'] for r in old_decisions+decisions}
    save('combined_thresholds.json',dict(decisions=old_decisions+decisions,previous_sixty_unchanged=True))
    save('threshold_freeze.json',dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),decisions_sha256=sha(HERE/'threshold_decisions.json'),combined_sha256=sha(HERE/'combined_thresholds.json'),before_checking=True))
    print('New tolerances frozen before checking',flush=True)
    isolated=check_isolated(selected,cases,decisions,new_forms)
    contexts=contextual_replay(selected,decisions,cases,calibration,combined,thresholds,forms)
    constructed=constructed_combined(cases,combined,thresholds,forms)
    regression=regressions(combined,thresholds,forms)
    corpus=speech(selected,decisions,combined,thresholds,forms)
    save('preservation.json',preservation())
    summary=dict(status='remaining37_trial_complete_not_integrated',new_terms=37,combined_terms=97,
        new_fuzzy_candidates=sum(r['selected_auto_threshold'] is not None for r in decisions),new_exact_only=sum(r['selected_auto_threshold'] is None for r in decisions),
        threshold_counts=dict(Counter(str(r['selected_auto_threshold']) for r in decisions)),
        isolated_checking=isolated['summary'],context_checking=contexts['summary'],combined_constructed_checking=constructed['summary'],
        previous60_context_regressions=len(contexts['previous60_regressions']),previous60_constructed_regressions=len(constructed['previous60_regression_ids']),
        previous_regression_cases=regression['cases'],previous_regressions_passed=regression['passed'],
        corpus_aggregate=corpus['aggregate'],unique_reference_occurrences_new37=corpus['unique_reference_occurrences_new37'],
        unique_reference_occurrences_all97=corpus['unique_reference_occurrences_all97'],
        new_variant_records=len(new_forms),all_variant_records=len(forms),thresholds_retuned_after_checking=False,corrected_rules_changed=False,
        new_asr_inference=False,controlled_intonation_variants_tested=0,independent_clinical_validation=False,integration_performed=False)
    save('summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
