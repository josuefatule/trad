"""Aggregate lexical scores and retain auditable review cases; no clinical WER."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from trad_lab.metrics import metrics, tokens, word_alignment
from trad_lab.m4.report import format_equivalence
from .verify import verify_result

TERMS=['hypertension','hypotension','orthostatic hypotension','non elevated blood pressure',
       'aldosteronism','primary aldosteronism','spironolactone','eplerenone',
       '57','50 seven','120 over 70','120 to 139','70 to 89','140 over 90','140 over 19',
       'not frail','normal kidney function','no','not','without','untreated',"i'm treated",
       'four to six years','46 years','diastolic','dystolic','micrograms per deciliter',
       'micrograms per decilator','spironolactam']


def inventory(text):
    sequence=tokens(text);result={}
    for term in TERMS:
        t=tokens(term)
        result[term]=sum(sequence[i:i+len(t)]==t for i in range(len(sequence)-len(t)+1))
    return result


def edit_spans(edits, operation):
    spans=[]
    for edit in edits:
        if edit['op']!=operation:continue
        index=edit['ref_index'] if operation=='D' else edit['hyp_index']
        word=edit['reference'] if operation=='D' else edit['hypothesis']
        if spans and index==spans[-1]['end']+1:
            spans[-1]['end']=index;spans[-1]['words'].append(word)
        else:spans.append({'start':index,'end':index,'words':[word]})
    return {'max_consecutive_words':max((len(s['words']) for s in spans),default=0),
            'longest_spans':sorted(spans,key=lambda s:len(s['words']),reverse=True)[:3],
            'scope':'Exact alignment against a provisional reference/hypothesis; not verified acoustic loss or duplication'}


def summarize(root):
    root=Path(root);rows=[];groups=defaultdict(list);verification=[];review=[]
    for path in sorted(root.glob('*/w*/**/result.json')):
        d=json.loads(path.read_text(encoding='utf-8'));run=path.relative_to(root).parts[0]
        config=path.parent.parent.name
        row={'run':run,'config':config,'sample':d['sample']['id'],'status':d['status'],'error':d['error'],
             'audio_s':d['audio_s'],'processed_s':d['processed_s'],'rtf':d['inference_rtf'],
             'words':d['final_word_count'],'stable_words':d['stable_word_count'],
             'eof_tail_words':len(tokens(d['eof_tail_text'])),'calls':d['calls'],
             'lag':d['serial_confirmation_lag_s'],'algorithmic_lag':d['confirmation_lag_s'],
             'peak_audio_samples':d['peak_audio_samples'],'peak_word_state':d['peak_word_state'],
             'path':str(path.resolve())}
        row['provisional_revision_updates']=(d.get('stats') or {}).get('provisional_revision_updates')
        for key in ('provisional_reference_metrics','stable_only_reference_metrics','offline_hypothesis_disagreement','wlk_hypothesis_disagreement'):
            if key in d:
                row[key]={k:d[key][k] for k in ('reference_words','hypothesis_words','substitutions','deletions','insertions','word_errors','wer','reference_characters','character_errors','cer','risk_flag_counts')}
        rows.append(row);groups[(run,config)].append(row)
        if run!='yeti_initial':
            try:verification.append({'path':str(path.resolve()),**verify_result(path)})
            except Exception as exc:verification.append({'path':str(path.resolve()),'status':'FAIL','error':str(exc)})
        if d['status']=='completed':
            text=d['final_text_with_unconfirmed_eof_tail']
            entry={'run':run,'config':config,'sample':d['sample']['id'],'candidate_inventory':inventory(text),
                   'reference_inventory':inventory(d['sample']['reference']) if d['sample'].get('reference') else None,
                   'eof_tail':d['eof_tail_text']}
            if 'provisional_reference_metrics' in d:
                entry['risk_review']=d['provisional_reference_metrics']['risk_flags']
                entry['all_word_edits']=d['provisional_reference_metrics']['word_edits']
                secondary=metrics(format_equivalence(d['sample']['reference']),format_equivalence(text))
                entry['secondary_format_review']={k:secondary[k] for k in ('word_errors','reference_words','wer','cer')}
                entry['secondary_format_scope']='Post-hoc %/percent and stage one/two format diagnostic only. Primary lexical scores and ASR text unchanged; not clinical WER.'
            elif 'offline_hypothesis_disagreement' in d:
                entry['risk_review']=d['offline_hypothesis_disagreement']['risk_flags']
                entry['all_word_edits']=d['offline_hypothesis_disagreement']['word_edits']
            if 'all_word_edits' in entry:
                entry['deletion_spans']=edit_spans(entry['all_word_edits'],'D')
                entry['insertion_spans']=edit_spans(entry['all_word_edits'],'I')
            review.append(entry)
    aggregates=[]
    for (run,config),items in groups.items():
        environment=root/run/'environment.json'
        group=json.loads(environment.read_text(encoding='utf-8'))['config_args']['group']
        expected=3 if group in ('full','clips') else 1
        complete=len(items)==expected and all(r['status']=='completed' for r in items)
        a={'run':run,'config':config,'completed':complete,'samples':len(items),
           'expected_samples':expected,'total_audio_s':sum(r['audio_s'] for r in items),'metrics_scope':'Provisional lexical reference, never clinical WER'}
        if complete and all('provisional_reference_metrics' in r for r in items):
            for prefix,key in [('final','provisional_reference_metrics'),('stable','stable_only_reference_metrics')]:
                errors=sum(r[key]['word_errors'] for r in items);words=sum(r[key]['reference_words'] for r in items)
                chars=sum(r[key]['reference_characters'] for r in items)
                a[prefix+'_wer']=errors/words;a[prefix+'_word_errors']=errors;a['reference_words']=words
                a[prefix+'_cer']=sum(r[key]['character_errors'] for r in items)/chars
        aggregates.append(a)
    output={'rows':rows,'aggregates':aggregates,'verification':verification,
            'interpretation':'Exact lexical edits and automated risk cues require listening/reference review. Timestamp windows verified independently; no medical reference inferred from ASR.'}
    (root/'comparison.json').write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding='utf-8')
    (root/'medical_review.json').write_text(json.dumps(review,indent=2,ensure_ascii=False),encoding='utf-8')
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');args=p.parse_args()
    d=summarize(args.root)
    print(json.dumps({'runs':len(d['rows']),'aggregates':d['aggregates'],
                      'verification_failures':[r for r in d['verification'] if r['status']!='PASS']}))
