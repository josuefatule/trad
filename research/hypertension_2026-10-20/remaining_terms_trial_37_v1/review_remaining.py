"""Audit the frozen expansion without changing tolerances or old evidence."""
from collections import Counter
import unicodedata
import evaluate_remaining as exp
from trad_lab.metrics import tokens,edit_distance,TOKEN


def apply(raw,changes):
    output=raw
    for c in sorted(changes,key=lambda c:c['start'],reverse=True):
        assert raw[c['start']:c['end']]==c['source']
        output=output[:c['start']]+c['replacement']+output[c['end']:]
    return output


def change_key(c):return tuple(c[k] for k in ['model','sample_id','start','end','replacement','canonical'])


def main():
    exp.sys.stdout.reconfigure(encoding='utf-8')
    if (exp.HERE/'review_findings.json').exists():raise SystemExit('Completed review cannot be overwritten')
    exp.verify_prior()
    corpus=exp.load(exp.HERE/'speech_comparison.json')
    before=[c for c in corpus['changes'] if c['profile']=='previous60_corrected']
    after=[c for c in corpus['changes'] if c['profile']=='combined97_individualized']
    before_keys={change_key(c) for c in before};after_keys={change_key(c) for c in after}
    introduced=[c for c in after if change_key(c) not in before_keys]
    removed=[c for c in before if change_key(c) not in after_keys]
    introduced_keys={change_key(c) for c in introduced}
    audit=[]
    for c in corpus['changes']:
        if c['profile'] not in ['new37_individualized','combined97_individualized']:continue
        record=exp.load(exp.prior.CACHED/'models'/c['model']/c['sample_id']/'result.json')
        raw,ref=record['hypothesis_raw'],record['reference_raw']
        single=apply(raw,[c]);delta=edit_distance(tokens(ref),tokens(single))-record['metrics']['word_errors']
        norm=unicodedata.normalize('NFKC',raw).casefold().replace('’',"'").replace('‘',"'")
        left=len(unicodedata.normalize('NFKC',raw[:c['start']]).casefold())
        right=len(unicodedata.normalize('NFKC',raw[:c['end']]).casefold())
        h_ids=[i for i,m in enumerate(TOKEN.finditer(norm)) if m.start()<right and m.end()>left]
        mapping=exp.prior.ref_map(tokens(ref),tokens(raw),record['metrics']['word_edits'])
        r_ids=[r for r,h in mapping.items() if h in h_ids]
        context=' '.join(tokens(ref)[max(0,min(r_ids)-5):max(r_ids)+6]) if r_ids else None
        group=[x for x in corpus['changes'] if x['model']==c['model'] and x['sample_id']==c['sample_id'] and x['profile']==c['profile']]
        entire=apply(raw,group);without=apply(raw,[x for x in group if x is not c])
        marginal=edit_distance(tokens(ref),tokens(entire))-edit_distance(tokens(ref),tokens(without))
        audit.append(dict(**c,introduced_by_expansion=change_key(c) in introduced_keys,
            word_error_delta_if_applied_alone=delta,word_error_delta_in_profile=marginal,
            assessment='lexical_agreement_improved' if marginal<0 else 'lexical_agreement_worsened' if marginal>0 else 'lexically_neutral',
            provisional_reference_context=context,independent_audio_or_clinical_adjudication=False))
    exp.save('correction_review.json',audit)
    exp.save('change_comparison.json',dict(previous60_changes=len(before),combined97_changes=len(after),
        retained_changes=len(before_keys&after_keys),introduced=introduced,removed=removed))
    model_comparison=[]
    for model in ['small','medium','large-v3-turbo']:
        rows={r['profile']:r for r in corpus['aggregate'] if r['model']==model}
        new_audit=[r for r in audit if r['model']==model and r['profile']=='combined97_individualized' and r['introduced_by_expansion']]
        model_comparison.append(dict(model=model,previous60_word_errors=rows['previous60_corrected']['word_errors'],
            combined97_word_errors=rows['combined97_individualized']['word_errors'],
            error_delta=rows['combined97_individualized']['word_errors']-rows['previous60_corrected']['word_errors'],
            previous60_wer=rows['previous60_corrected']['wer'],combined97_wer=rows['combined97_individualized']['wer'],
            new37_alone_word_errors=rows['new37_individualized']['word_errors'],
            new37_uniform_word_errors=rows['new37_uniform090']['word_errors'],
            introduced_changes=len(new_audit),introduced_assessment_counts=dict(Counter(r['assessment'] for r in new_audit))))
    terms=exp.load(exp.HERE/'term_results.json');counts={}
    for group in ['new37','previous60']:
        by_term=[]
        for r in terms:
            if r['group']!=group:continue
            baseline='raw' if group=='new37' else 'previous60_corrected'
            delta=r['results']['combined97_individualized']['exact_reference_form']-r['results'][baseline]['exact_reference_form']
            by_term.append(dict(concept_id=r['concept_id'],canonical_en=r['canonical_en'],delta=delta,
                before=r['results'][baseline]['exact_reference_form'],after=r['results']['combined97_individualized']['exact_reference_form'],
                observations=r['results'][baseline]['observations']))
        counts[group]=dict(improved=sum(r['delta']>0 for r in by_term),unchanged=sum(r['delta']==0 for r in by_term),worsened=sum(r['delta']<0 for r in by_term),rows=by_term)
    all_improved_or_equal=all(r['error_delta']<=0 for r in model_comparison)
    context=exp.load(exp.HERE/'context_comparison.json');checking=exp.load(exp.HERE/'combined_checking.json')
    findings=dict(status='frozen_expansion_review_complete_not_integrated',model_comparison=model_comparison,
        previous60_changes=len(before),combined97_changes=len(after),introduced_changes=len(introduced),removed_changes=len(removed),
        introduced_assessments=dict(Counter(r['assessment'] for r in audit if r['profile']=='combined97_individualized' and r['introduced_by_expansion'])),
        new37_alone_assessments=dict(Counter(r['assessment'] for r in audit if r['profile']=='new37_individualized')),
        term_literal_agreement=counts,aggregate_no_worse_in_any_model=all_improved_or_equal,
        previous60_context_regressions=len(context['previous60_regressions']),previous60_constructed_regressions=len(checking['previous60_regression_ids']),
        thresholds_retuned_after_checking=False,corrected_rules_changed=False,
        independent_holdout=False,clinical_validation=False,integration_performed=False)
    exp.save('review_findings.json',findings)
    print(exp.json.dumps({k:v for k,v in findings.items() if k!='term_literal_agreement'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
