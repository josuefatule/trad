"""Post-checking diagnostics only: never recalibrate or change frozen outputs."""
from collections import Counter, defaultdict
from dataclasses import asdict
import unicodedata
import evaluate_50 as trial
from app.captions.terminology_normalizer import _source_tokens
from trad_lab.metrics import tokens, edit_distance, TOKEN

HERE=trial.HERE
load=trial.prior.load
save=trial.save


def corrections(corpus):
    rows=[]
    for change in corpus['changes']:
        if change['profile']!='new50_individualized_guarded':continue
        record=load(trial.prior.CACHED/'models'/change['model']/change['sample_id']/'result.json')
        raw,ref=record['hypothesis_raw'],record['reference_raw']
        assert raw[change['start']:change['end']]==change['source']
        once=raw[:change['start']]+change['replacement']+raw[change['end']:]
        errors=edit_distance(tokens(ref),tokens(once))
        delta=errors-record['metrics']['word_errors']
        norm=unicodedata.normalize('NFKC',raw).casefold().replace('’',"'").replace('‘',"'")
        left=len(unicodedata.normalize('NFKC',raw[:change['start']]).casefold())
        right=len(unicodedata.normalize('NFKC',raw[:change['end']]).casefold())
        h_indices=[i for i,m in enumerate(TOKEN.finditer(norm)) if m.start()<right and m.end()>left]
        mapping=trial.prior.ref_map(tokens(ref),tokens(raw),record['metrics']['word_edits'])
        r_indices=[r for r,h in mapping.items() if h in h_indices]
        context=' '.join(tokens(ref)[max(0,min(r_indices)-5):max(r_indices)+6]) if r_indices else None
        source_words,target_words=tokens(change['source']),tokens(change['replacement'])
        plural_loss=any(a==b+'s' for a,b in zip(source_words,target_words)) and len(source_words)==len(target_words)
        rows.append(dict(**change,word_error_delta_if_applied_alone=delta,
            provisional_reference_context=context,
            assessment='lexical_agreement_improved' if delta<0 else 'lexical_agreement_worsened' if delta>0 else 'lexically_neutral',
            observed_plural_to_singular=plural_loss,
            observed_pharmacologic_canonicalization=source_words==['pharmacologic','therapy'],
            independent_audio_or_clinical_adjudication=False))
    return rows


def overlap(selected,thresholds):
    cases={r['case_id']:r for r in load(HERE/'context_cases.json')}
    results=load(HERE/'context_comparison.json')['rows']
    failed=[r for r in results if r['profile']=='individualized_guarded' and r['positive']
            and r['calibration_repairable'] and not r['exact_expected_output']]
    counts=Counter(cases[r['case_id']]['concept_id'] for r in failed)
    rows=[]
    for cid,count in counts.items():
        case=next(r for r in failed if cases[r['case_id']]['concept_id']==cid)
        item=next(s for s in selected if s['concept_id']==cid)
        isolated=trial.ctx.candidate(case['text'],[item],thresholds)
        obj=trial.ctx.ContextNormalizer.from_documents([trial.ctx.document(selected,thresholds)],trial.ctx.NormalizerConfig())
        src=_source_tokens(case['text'])
        exact=obj._select(obj._exact_matches(case['text'],src))
        reserved={i for match in exact for i in range(match.start_token,match.end_token)}
        fuzzy=obj._fuzzy_matches(case['text'],src)
        long=[m for m in fuzzy if m.term.canonical==item['canonical_en'] and m.action=='auto']
        def describe(m):
            return dict(source=case['text'][m.start:m.end],canonical=m.term.canonical,
                        start=m.start,end=m.end,start_token=m.start_token,end_token=m.end_token,
                        confidence=m.confidence,action=m.action,rule=m.rule)
        intended=[]
        for match in long:
            blockers=[m for m in exact if set(range(m.start_token,m.end_token)) & set(range(match.start_token,match.end_token))]
            intended.append(dict(**describe(match),overlapping_reserved_exact=[describe(m) for m in blockers]))
        selected_fuzzy=obj._select(fuzzy,reserved)
        rows.append(dict(concept_id=cid,canonical_en=item['canonical_en'],failed_contexts=count,
            example_case_id=case['case_id'],input=case['text'],expected=case['expected'],
            isolated_output=isolated['text'],all50_output=case['output'],
            isolated_recovers=isolated['text']==case['expected'],
            all50_recovers=case['exact_expected_output'],exact_reservations=[describe(m) for m in exact],
            auto_fuzzy_intended_candidates=intended,
            intended_selected_after_exact_reservation=any(m.term.canonical==item['canonical_en'] for m in selected_fuzzy),
            diagnosis='Exact subterms reserve overlapping tokens before fuzzy phrase selection; raising/lowering tolerance alone does not change that priority.',
            post_checking_diagnostic=True,threshold_or_guard_changed=False))
    assert len(rows)==6 and sum(counts.values())==42
    assert all(r['isolated_recovers'] and not r['all50_recovers'] for r in rows)
    assert all(r['auto_fuzzy_intended_candidates'] and not r['intended_selected_after_exact_reservation'] for r in rows)
    assert all(any(m['overlapping_reserved_exact'] for m in r['auto_fuzzy_intended_candidates']) for r in rows)
    return rows


def variant_record():
    document=load(trial.BASE/'integration_candidate/form_decisions.json')
    matches=[]
    def walk(node):
        if isinstance(node,dict):
            if node.get('form')=='pharmacologic therapy' and 'form_id' in node:matches.append(node)
            for value in node.values():walk(value)
        elif isinstance(node,list):
            for value in node:walk(value)
    walk(document)
    assert len(matches)==1
    return dict(existing_research_record=matches[0],
        interpretation='Existing research lexical variant; literal attestation is not semantic approval and automatic substitution is explicitly not approved. The corpus already uses this spelling: canonicalization adds lexical errors without demonstrated ASR repair.',
        new_web_verification=False,original_record_changed=False)


def main():
    trial.sys.stdout.reconfigure(encoding='utf-8')
    if (HERE/'review_findings.json').exists():raise SystemExit('Existing review is immutable')
    trial.verify_inputs()
    frozen=load(HERE/'threshold_freeze.json')
    assert trial.prior.sha(HERE/'threshold_decisions.json')==frozen['decisions_sha256']
    selected=load(HERE/'selection.json')['selected']
    decisions=load(HERE/'threshold_decisions.json')
    thresholds={r['concept_id']:r['selected_auto_threshold'] for r in decisions}
    corpus=load(HERE/'speech_comparison.json')
    audited=corrections(corpus);save('correction_review.json',audited)
    diagnostics=overlap(selected,thresholds);save('overlap_diagnostics.json',diagnostics)
    provenance=variant_record();save('variant_provenance.json',provenance)
    # Real checking discovered omissions in the fixed plural guards. These probes
    # document the gap after checking, never feed the threshold selection.
    probes=[]
    for text in ['diastolic blood pressures','cardiovascular risks']:
        result=trial.ctx.candidate(text,selected,thresholds)
        probes.append(dict(input=text,expected_preservation=text,output=result['text'],
            preserved=result['text']==text,changes=result['changes'],
            post_checking_diagnostic=True,used_for_calibration=False))
    save('postchecking_plural_probes.json',probes)
    per_model=[]
    for model in ['small','medium','large-v3-turbo']:
        subset=[r for r in audited if r['model']==model]
        groups=[]
        for canonical in dict.fromkeys(r['canonical'] for r in subset):
            group=[r for r in subset if r['canonical']==canonical]
            groups.append(dict(canonical=canonical,changes=len(group),word_error_delta=sum(r['word_error_delta_if_applied_alone'] for r in group)))
        actual={r['profile']:r for r in corpus['aggregate'] if r['model']==model}
        summed=sum(r['word_error_delta_if_applied_alone'] for r in subset)
        assert summed==actual['new50_individualized_guarded']['word_errors']-actual['raw']['word_errors']
        per_model.append(dict(model=model,changes=len(subset),assessment_counts=dict(Counter(r['assessment'] for r in subset)),
            word_error_delta=summed,canonicalization_changes=sum(r['observed_pharmacologic_canonicalization'] for r in subset),
            plural_losses=sum(r['observed_plural_to_singular'] for r in subset),by_term=groups))
    terms=load(HERE/'term_results.json')
    counts=Counter()
    for r in terms:
        delta=r['results']['new50_individualized_guarded']['exact_reference_form']-r['results']['raw']['exact_reference_form']
        counts['improved' if delta>0 else 'worsened' if delta<0 else 'unchanged']+=1
    findings=dict(status='review_complete_frozen_trial_not_integrated',
        conclusion='No aggregate lexical improvement from the fifty-term expansion; retain as research and do not approve the profile for integration.',
        correction_counts=dict(Counter(r['assessment'] for r in audited)),per_model=per_model,
        simulated_new50_changes=len(audited),term_literal_agreement_counts=dict(counts),
        extra_context_overlap_failures=42,affected_overlap_terms=6,
        plural_guard_gaps=[r['input'] for r in probes if not r['preserved']],
        lexical_variant_record_id=provenance['existing_research_record']['form_id'],
        thresholds_retuned_after_checking=False,frozen_guards_changed=False,
        controlled_intonation_variants_tested=0,new_asr_inference=False,
        independent_clinical_adjudication=False,integration_performed=False)
    assert len(audited)==27
    save('review_findings.json',findings)
    print(trial.json.dumps(findings,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
