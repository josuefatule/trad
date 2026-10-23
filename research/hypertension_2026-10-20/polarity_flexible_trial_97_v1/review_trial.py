"""Review the refined fixed-cap experiment; do not optimize on the replay."""
from collections import Counter
from pathlib import Path
import run_flexible as exp

HERE=exp.HERE
FINAL=HERE/'visible_root_refinement_v2'


def key(c):return tuple(c[k] for k in ['model','sample_id','start','end','replacement','canonical'])
def apply(raw,changes):
    text=raw
    for c in sorted(changes,key=lambda c:c['start'],reverse=True):
        assert raw[c['start']:c['end']]==c['source']
        text=text[:c['start']]+c['replacement']+text[c['end']:]
    return text


def main():
    exp.sys.stdout.reconfigure(encoding='utf-8')
    if (HERE/'review_findings.json').exists():raise SystemExit('Completed review is immutable')
    corpus=exp.load(FINAL/'speech_comparison.json')
    profiles=[p for p in exp.PROFILES if p.startswith('direction_guard')]
    before={key(c) for c in corpus['changes'] if c['profile']=='previous97'}
    audit=[]
    for c in corpus['changes']:
        if c['profile'] not in profiles:continue
        record=exp.load(exp.old.prior.CACHED/'models'/c['model']/c['sample_id']/'result.json')
        raw,reference=record['hypothesis_raw'],record['reference_raw']
        group=[x for x in corpus['changes'] if x['model']==c['model'] and x['sample_id']==c['sample_id'] and x['profile']==c['profile']]
        full=apply(raw,group);without=apply(raw,[x for x in group if x is not c])
        delta=exp.edit_distance(exp.tokens(reference),exp.tokens(full))-exp.edit_distance(exp.tokens(reference),exp.tokens(without))
        audit.append(dict(**c,introduced_vs_previous97=key(c) not in before,word_error_delta_in_profile=delta,
            assessment='lexical_agreement_improved' if delta<0 else 'lexical_agreement_worsened' if delta>0 else 'lexically_neutral',
            independent_audio_or_clinical_adjudication=False))
    exp.save('correction_review.json',audit)
    dataset={name:exp.load(FINAL/(name+'_comparison.json')) for name in ['pressure','constructed','context','regression']}
    negatives=[];losses=[]
    for name,data in dataset.items():
        before_rows={r['case_id']:r for r in data['rows'] if r['profile']=='previous97'}
        for profile in profiles:
            rows=[r for r in data['rows'] if r['profile']==profile]
            grouped={}
            for r in rows:
                if not r['negative_changed']:continue
                k=(r['input'],r['output'])
                if k not in grouped:grouped[k]=dict(input=r['input'],output=r['output'],case_ids=[],changes=r['changes'])
                grouped[k]['case_ids'].append(r['case_id'])
            negatives.append(dict(dataset=name,profile=profile,cases=sum(r['negative_changed'] for r in rows),unique_input_output_pairs=len(grouped),examples=list(grouped.values())))
            lost=[r for r in rows if before_rows[r['case_id']]['passed'] and not r['passed']]
            losses.append(dict(dataset=name,profile=profile,lost_cases=len(lost),rows=lost))
    exp.save('negative_change_review.json',negatives);exp.save('recovery_loss_review.json',losses)
    comparison=[]
    for model in ['small','medium','large-v3-turbo']:
        rows={r['profile']:r for r in corpus['aggregate'] if r['model']==model}
        comparison.append(dict(model=model,profiles={p:dict(word_errors=rows[p]['word_errors'],wer=rows[p]['wer'],delta_vs_previous97=rows[p]['word_errors']-rows['previous97']['word_errors']) for p in ['previous97']+profiles}))
    eligibility=[]
    for profile in profiles:
        failures={name:next(r for r in data['summary'] if r['profile']==profile)['negative_changed'] for name,data in dataset.items()}
        eligibility.append(dict(profile=profile,negative_changes=failures,no_negative_rewrites_in_tested_cases=all(v==0 for v in failures.values())))
    findings=dict(status='review_complete_research_only',model_comparison=comparison,
        negative_rewrite_eligibility=eligibility,
        pressure_specific_control_fixed=all(next(r for r in dataset['pressure']['summary'] if r['profile']==p)['negative_changed']==0 for p in profiles),
        flexible_caps=[.92,.90,.88],all_flexible_caps_have_other_negative_changes=all(not r['no_negative_rewrites_in_tested_cases'] for r in eligibility if r['profile']!='direction_guard_same'),
        recommendation='Retain the directional guard as laboratory work. Do not approve a global tolerance reduction: every flexible cap has non-pressure negative rewrites. Per-term limits and additional protections need a separate experiment.',
        refinement_and_first_attempt_preserved=True,independent_holdout=False,clinical_adjudication=False,integration_performed=False)
    exp.save('review_findings.json',findings)
    print(exp.json.dumps(findings,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
