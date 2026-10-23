"""Keep the first trial; refine only previously ambiguous visible roots."""
from datetime import datetime,timezone
from pathlib import Path
import subprocess
import sys
import pressure_refined as refined
import run_flexible as exp

HERE=Path(__file__).resolve().parent
FIRST=HERE.parent


def replay_refined(name,cases):
    initial=exp.load(FIRST/(name+'_comparison.json'))
    index={(r['profile'],r['case_id']):r for r in initial['rows']}
    rows=[];summaries=[];reuse={}
    for profile in exp.PROFILES:
        group=[];reused=0
        for c in cases:
            old=index[(profile,c['case_id'])]
            if not profile.startswith('direction_guard') or old['direction_guard_blocks']==0:
                row=dict(old,reused_first_revision_output=True)
                reused+=1
            else:
                r=exp.candidate(c['text'],profile)
                passed=exp.tokens(r['text'])==exp.tokens(c['expected']) if name=='constructed' and c['positive'] else r['text']==c['expected']
                row=dict(profile=profile,case_id=c['case_id'],kind=c.get('kind'),positive=c['positive'],
                    input=c['text'],expected=c['expected'],output=r['text'],passed=passed,
                    negative_changed=not c['positive'] and r['text']!=c['text'],changes=r['changes'],
                    direction_sequence_changed=refined.direction_signature(c['text'])['directions']!=refined.direction_signature(r['text'])['directions'],
                    direction_guard_blocks=sum('pressure_direction_changed_or_unproven' in b['reasons'] for b in r['blocked']),reused_first_revision_output=False)
            group.append(row)
        rows+=group;reuse[profile]=reused
        summaries.append(dict(profile=profile,cases=len(group),positive_cases=sum(r['positive'] for r in group),
            positive_correct=sum(r['positive'] and r['passed'] for r in group),negative_cases=sum(not r['positive'] for r in group),
            negative_changed=sum(r['negative_changed'] for r in group),passed=sum(r['passed'] for r in group),
            cases_blocked_by_direction_guard=sum(r['direction_guard_blocks']>0 for r in group)))
    baseline={r['case_id']:r for r in rows if r['profile']=='previous97'}
    transitions=[]
    for profile in exp.PROFILES[1:]:
        group=[r for r in rows if r['profile']==profile]
        transitions.append(dict(profile=profile,improved_case_ids=[r['case_id'] for r in group if r['passed'] and not baseline[r['case_id']]['passed']],
            regressed_case_ids=[r['case_id'] for r in group if not r['passed'] and baseline[r['case_id']]['passed']],
            newly_changed_negative_ids=[r['case_id'] for r in group if r['negative_changed'] and not baseline[r['case_id']]['negative_changed']]))
    data=dict(summary=summaries,rows=rows,transitions=transitions,reused_output_counts=reuse,
        reuse_reason='The only refinement is AMBIGUOUS -> explicit visible root; cases with zero first-revision directional vetoes have identical candidate filtering. All vetoed constructed cases are recomputed. Speech is recomputed whenever a prior directional veto becomes admissible; otherwise identical filtering and output are proven from the full veto audit. Identical-text metrics are reused.')
    exp.save(name+'_comparison.json',data);print('Refined '+name+' complete',flush=True)
    return data


def replay_speech():
    initial=exp.load(FIRST/'speech_comparison.json')
    selected,profiles,variants=exp.INPUTS
    sources=exp.load(exp.old.prior.CACHED/'inputs/inputs.json')
    positions=exp.load(exp.PREVIOUS/'reference_occurrences.json')
    old_rows={(r['model'],r['sample_id'],r['profile']):r for r in initial['rows']}
    old_outputs={(r['model'],r['sample_id'],r['profile']):r for r in initial['outputs']}
    rows=[];outputs=[];changes=[];observations=[];identical_measurements=0
    for model in ['small','medium','large-v3-turbo']:
        for sample in sources:
            sid=sample['id'];record=exp.load(exp.old.prior.CACHED/'models'/model/sid/'result.json')
            raw,reference=record['hypothesis_raw'],record['reference_raw']
            for profile in ['raw']+exp.PROFILES:
                key=(model,sid,profile);before=old_outputs[key]
                freed=[b for b in before['blocked'] if 'pressure_direction_changed_or_unproven' in b['reasons'] and refined.direction_verdict(b['source'],b['canonical'])['accepted']] if profile.startswith('direction_guard') else []
                if not profile.startswith('direction_guard') or not freed:
                    output=dict(before)
                    these=[dict(c) for c in initial['changes'] if (c['model'],c['sample_id'],c['profile'])==key]
                    if profile.startswith('direction_guard'):
                        updated=[]
                        for b in before['blocked']:
                            if 'pressure_direction_changed_or_unproven' in b['reasons']:
                                verdict=refined.direction_verdict(b['source'],b['canonical'])
                                updated.append(dict(b,source_signature=verdict['source_signature'],target_signature=verdict['target_signature']))
                            else:updated.append(dict(b))
                        output.update(blocked=updated,reused_identical_candidate_filter=True,newly_admissible_directional_candidates=0)
                else:
                    result=exp.candidate(raw,profile)
                    output=dict(model=model,sample_id=sid,profile=profile,candidate_text=result['text'],
                        original_hypothesis_sha256=before['original_hypothesis_sha256'],blocked=result['blocked'],
                        preserved_variants=result['preserved_variants'],identifier_protections=result['identifier_protections'],overlap_resolutions=result['overlap_resolutions'])
                    output.update(reused_identical_candidate_filter=False,newly_admissible_directional_candidates=len(freed))
                    these=[dict(model=model,sample_id=sid,profile=profile,**c) for c in result['changes']]
                text=output['candidate_text']
                if text==before['candidate_text']:
                    row=dict(old_rows[key]);identical_measurements+=1
                    observations.extend(dict(r) for r in initial['occurrences'] if (r['model'],r['sample_id'],r['profile'])==key)
                else:
                    measured=exp.metrics(reference,text);mapped=exp.old.prior.ref_map(exp.tokens(reference),exp.tokens(text),measured['word_edits'])
                    row=dict(model=model,sample_id=sid,profile=profile,word_errors=measured['word_errors'],reference_words=measured['reference_words'],wer=measured['wer'],
                        character_errors=measured['character_errors'],reference_characters=measured['reference_characters'],
                        cue_signature_changed=exp.old.prior.cue_signature(raw)!=exp.old.prior.cue_signature(text),
                        function_word_sequence_changed=[w for w in refined.previous.first.ctx._tokens(raw) if w in refined.previous.first.ctx.FUNCTION_WORDS]!=[w for w in refined.previous.first.ctx._tokens(text) if w in refined.previous.first.ctx.FUNCTION_WORDS])
                    for p in positions:
                        if p['sample_id']!=sid:continue
                        phrase,_=exp.old.prior.extracted_span(p['ref_left'],p['ref_right'],mapped,exp.tokens(text),measured['word_edits'])
                        observations.append(dict(**p,model=model,profile=profile,observed_tokens=phrase,exact_reference_form=phrase==p['reference_tokens']))
                row.update(simulated_changes=len(these),direction_sequence_changed=refined.direction_signature(raw)['directions']!=refined.direction_signature(text)['directions'])
                rows.append(row);outputs.append(output);changes+=these
            print(f'Refined speech predictions: {model}/{sid}',flush=True)
    aggregate=[]
    for model in ['small','medium','large-v3-turbo']:
        for profile in ['raw']+exp.PROFILES:
            group=[r for r in rows if r['model']==model and r['profile']==profile]
            errors=sum(r['word_errors'] for r in group);words=sum(r['reference_words'] for r in group)
            aggregate.append(dict(model=model,profile=profile,word_errors=errors,reference_words=words,wer=errors/words,
                simulated_changes=sum(r['simulated_changes'] for r in group),samples_with_changed_cues=sum(r['cue_signature_changed'] for r in group),
                samples_with_changed_function_words=sum(r['function_word_sequence_changed'] for r in group),samples_with_changed_direction_sequence=sum(r['direction_sequence_changed'] for r in group)))
    data=dict(aggregate=aggregate,rows=rows,outputs=outputs,changes=changes,occurrences=observations,unique_reference_occurrences=310,
        identical_text_measurement_reuses=identical_measurements,new_asr_inference=False,
        replay_scope='All changed directional vetoes re-evaluated; native candidate selection rerun where any veto becomes admissible. Other outputs have provably identical candidate filtering. Baseline/control and identical-text measurements reused from the preserved first revision.')
    exp.save('speech_comparison.json',data)
    terms=[]
    for item in selected:
        results={}
        for profile in ['raw']+exp.PROFILES:
            group=[r for r in observations if r['concept_id']==item['concept_id'] and r['profile']==profile]
            results[profile]=dict(observations=len(group),exact_reference_form=sum(r['exact_reference_form'] for r in group))
        terms.append(dict(**item,thresholds={p:profiles[p][item['concept_id']] for p in exp.PROFILES},results=results,operational_approval=False))
    exp.save('term_results.json',terms);return data


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if (HERE/'protocol.json').exists():raise SystemExit('Second revision already frozen')
    if not (FIRST/'summary.json').exists():raise SystemExit('First trial is still running')
    exp.verify_prior()
    for r in exp.load(FIRST/'protocol.json')['source_hashes']:assert exp.sha(exp.ROOT/r['path'])==r['sha256']
    if not (FIRST/'first_replay_manifest.json').exists():
        exp.save('first_replay_manifest.json',dict(files=[dict(name=p.name,bytes=p.stat().st_size,sha256=exp.sha(p)) for p in sorted(FIRST.iterdir()) if p.is_file()],first_trial_preserved=True))
    for name in ['baseline.json','inputs.json','pressure_cases.json','constructed_cases.json','context_cases.json','existing_regression_cases.json']:
        path=HERE/name
        if path.exists():assert path.read_bytes()==(FIRST/name).read_bytes()
        else:path.write_bytes((FIRST/name).read_bytes())
    tested=subprocess.run([sys.executable,'-B',str(HERE/'test_refined.py')],capture_output=True,text=True,encoding='utf-8',cwd=exp.ROOT)
    exp.HERE=HERE
    exp.save('development_tests.json',dict(returncode=tested.returncode,output=tested.stdout+tested.stderr))
    if tested.returncode:raise SystemExit(tested.stdout+tested.stderr)
    exp.save('protocol.json',dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        refinement='Only AMBIGUOUS markers with a literal hyper/hypo root and at most two suffix spelling edits become proven directional markers; missing/ambiguous direction still abstains.',
        reuse='Recompute every previously vetoed constructed case; for speech rerun native selection if any logged directional veto becomes admissible, otherwise prove unchanged candidate filtering and reuse its output. Reuse metrics only for byte-identical output text.',
        first_trial_preserved=True,first_protocol_sha256=exp.sha(FIRST/'protocol.json'),same_97_terms=True,same_caps=True,
        sources=[dict(name=p.name,sha256=exp.sha(p)) for p in [HERE/'pressure_refined.py',HERE/'run_refined.py',HERE/'test_refined.py']],
        inputs_sha256=exp.sha(HERE/'inputs.json'),independent_holdout=False,new_asr_inference=False,integration_performed=False))
    exp.INPUTS=exp.inputs();exp.guard=refined
    pressure=replay_refined('pressure',exp.load(HERE/'pressure_cases.json'))
    constructed=replay_refined('constructed',exp.load(HERE/'constructed_cases.json'))
    context=replay_refined('context',exp.load(HERE/'context_cases.json'))
    regression=replay_refined('regression',exp.load(HERE/'existing_regression_cases.json'))
    corpus=replay_speech()
    exp.save('summary.json',dict(status='refined_flexible_trial_complete_not_integrated',same_97_terms=True,active_terms=80,exact_only_terms=17,
        pressure_controls=pressure['summary'],constructed=constructed['summary'],contexts=context['summary'],regressions=regression['summary'],
        corpus_aggregate=corpus['aggregate'],unit_tests_passed=True,refinement_designed_after_first_trial=True,
        policies_or_caps_retuned_after_this_replay=False,independent_holdout=False,new_asr_inference=False,clinical_adjudication=False,integration_performed=False))
    print(exp.json.dumps(dict(pressure=pressure['summary'],constructed=constructed['summary'],contexts=context['summary'],corpus=corpus['aggregate']),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
