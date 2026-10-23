"""Transparent evaluation channels, separate from the recognizer."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import numpy as np
from trad_lab.audio import digest
from trad_lab.metrics import metrics, tokens, word_alignment, risk_categories
from trad_lab.runner import save
from trad_lab.m4c.replay import distribution
from trad_lab.m4c.verify import verify_result
from trad_lab.m4c.summarize import edit_spans, inventory
from .evaluate import ROOT, PRIOR, M3, CASES, MODELS


def phrase_status(case,text):
    """Only specified expression variants; never rewrites recognition text."""
    normal=' '.join(tokens(text))
    patterns={
      'ORTHO':r'\borthostatic hypotension\b',
      'UNTREATED':r'\buntreated stage (two|2) hypertension\b',
      'YEARS':r'\bevery (four to six|4 to 6) years\b',
      'BP140':r'\b(140 over 90|one hundred (and )?forty over ninety)\b'}
    wrong={
      'ORTHO':r'\borthostatic hypertension\b',
      'UNTREATED':r"\b(i'm treated|treated stage (two|2) hypertension)\b",
      'YEARS':r'\b(46|forty six) years\b',
      'BP140':r'\b140 over (19|nineteen)\b'}
    good=bool(re.search(patterns[case],normal));bad=bool(re.search(wrong[case],normal))
    return {'status':'conflicting_forms' if good and bad else 'matches_user_expression' if good else 'known_critical_conflict' if bad else 'expression_not_matched_review',
            'matched':good,'critical_conflict':bad,'scope':'Expression-level review against user provisional adjudication; not whole-clip WER or clinical validation'}


def sensitive_changes(before,after):
    """Alerts only: lexical changes, including morphological treatment negation."""
    a,b=tokens(before),tokens(after)
    if a==b:return []
    distance,edits=word_alignment(a,b)
    categories=set()
    for edit in edits:
        r,h=edit['reference'],edit['hypothesis']
        categories.update(risk_categories([r,h]))
        if any(x in {'untreated','treated',"i'm",'untreat','normotensive','hypertensive','hypotensive'} for x in (r,h)):
            categories.add('treatment_or_morphological_polarity')
        if any(x in {'aldosteronism','aldosterone','diastolic','systolic','spironolactam','spironolactone','spironolactinone'} for x in (r,h)):
            categories.add('medical_terminology')
    if re.search(r'\b(four to six|4 to 6)\b',' '.join(a+b)) and ('46' in a or '46' in b):
        categories.add('range_to_single_value')
    return sorted(categories)


def freeze_check_regions(out):
    """Define text checking masks before reviewing new full-corpus results."""
    inputs=json.loads((M3/'inputs/inputs.json').read_text(encoding='utf-8'))
    rows=[]
    for sample in inputs:
        reference=tokens(sample['reference_raw']);excluded=set();ranges=[]
        for name,(case,phrase) in CASES.items():
            sid='cardio_01' if name.startswith('cardio01') else 'cardio_03'
            if sid!=sample['id']:continue
            target=tokens(phrase.replace('stage two','stage 2') if case=='UNTREATED' else phrase)
            hits=[i for i in range(len(reference)-len(target)+1) if reference[i:i+len(target)]==target]
            if len(hits)!=1:raise ValueError('Reference expression locator ambiguous: '+case)
            start=max(0,hits[0]-60);end=min(len(reference),hits[0]+len(target)+60)
            excluded.update(range(start,end));ranges.append({'case':case,'start_token':start,'end_token_exclusive':end})
        rows.append({'id':sample['id'],'reference_sha256':sample['reference_sha256'],
            'reference_words':len(reference),'excluded_selection_token_indices':sorted(excluded),
            'checking_words':len(reference)-len(excluded),'selection_ranges':ranges})
    save(out/'checking_regions.json',{'policy':'Exclude 60 reference tokens on each side of each of the four selection expressions. No audio removed or changed. Full-file WER/CER still primary. Insertions assigned to deterministic ref_index.',
         'independence':'Within-corpus checking only; M3/M4-C previously examined corpus. No independent speakers claimed.', 'samples':rows})


def source_provenance(out):
    import av
    data=json.loads((M3/'inputs/inputs.json').read_text(encoding='utf-8'))
    rows=[]
    for s in data:
        with av.open(s['audio_path']) as container:
            rows.append({'id':s['id'],'source_sha256':digest(s['audio_path']),
                'matches_M3_hash':digest(s['audio_path'])==s['audio_sha256'],
                'metadata':dict(container.metadata),'duration_s':s['audio']['duration_s'],
                'reference_first_70_words':' '.join(tokens(s['reference_raw'])[:70]),
                'reference_last_70_words':' '.join(tokens(s['reference_raw'])[-70:])})
    # No title/URL/speaker identity is recoverable from these container tags.
    save(out/'source_provenance.json',{'files':rows,
        'observed_boundary':'cardio02 ends: associated with step-wise; cardio03 starts: increase in coronary artery calcium scores.',
        'inference':'Content continuity and matching encoder/container tags support the user suspicion that 02/03 are adjacent portions of one webinar. No original URL/session identifier available to certify it.',
        'conservative_grouping':{'group_A':['cardio_01'],'group_B':['cardio_02','cardio_03']},
        'independent_lecture_count':'At most two inferred source groups; three files are not three independent discourses.',
        'split':'cardio02 wholly checking, excluding prior exploratory exposure; 01/03 have selection regions excluded from secondary checking metrics.'})


def baseline_results():
    folder=PRIOR/'full_adaptive_vad/w15_u2_a2_adaptive'
    for path in sorted(folder.glob('*/result.json')):yield 'small',path,'M4-C baseline reused'
    path=PRIOR/'yeti_adaptive/w15_u2_a2_adaptive/yeti_received_full/result.json'
    yield 'small',path,'M4-C baseline reused'


def case_excerpt(words,start,end):
    return ''.join(w['text'] for w in words if w['end']>=start and w['start']<=end)


def complete_group(items,group):
    expected={'cardio_01','cardio_02','cardio_03'} if group=='full' else {'yeti_received_full'}
    return (len(items)==len(expected) and {r['sample'] for r in items}==expected
            and all(r['status']=='completed' for r in items))


def analyze(out):
    adjudications=json.loads((out/'adjudication.json').read_text(encoding='utf-8'))
    rows=[]
    for name in MODELS:
        folder=out/'offline'/name
        for path in sorted(folder.glob('*.json')):
            d=json.loads(path.read_text(encoding='utf-8'))
            if 'hypothesis_raw' not in d:continue
            item={'model':name,'input':d['input']['id'],'case':d['input'].get('case'),
                  'condition':d['input']['condition'],'text':d['hypothesis_raw'],'asr_s':d['asr_s'],
                  'input_sha256':d['input']['sha256'],'result_path':str(path.resolve()),'result_sha256':digest(path)}
            if item['case']:item['expression_review']=phrase_status(item['case'],item['text'])
            rows.append(item)
    save(out/'offline_matrix.json',rows)
    checking=json.loads((out/'checking_regions.json').read_text(encoding='utf-8'))
    masks={s['id']:s for s in checking['samples']}
    sources=list(baseline_results())
    sources.extend((p.relative_to(out/'incremental').parts[0],p,'M4-D measured') for p in sorted((out/'incremental').glob('*/*/*/result.json')))
    results=[];alerts=[];case_rows=[];pooled={}
    for name,path,provenance in sources:
        d=json.loads(path.read_text(encoding='utf-8'));sid=d['sample']['id']
        events=[json.loads(l) for l in (path.parent/'events.jsonl').read_text(encoding='utf-8').splitlines()]
        row={'model':name,'sample':sid,'provenance':provenance,'path':str(path.resolve()),'sha256':digest(path),
             'status':d['status'],'error':d['error'],'audio_s':d['audio_s'],'processed_s':d['processed_s'],
             'inference_rtf':d['inference_rtf'],'stable_words':d['stable_word_count'],
             'eof_tail':d['eof_tail_text'],'eof_tail_words':len(tokens(d['eof_tail_text'])),
             'stats':d['stats'],'serial_lag':d['serial_confirmation_lag_s'],'algorithmic_lag':d['confirmation_lag_s'],
             'peak_audio_samples':d['peak_audio_samples'],'peak_word_state':d['peak_word_state'],
             'inventory_stable':inventory(d['stable_text']),
             'verification':verify_result(path)}
        if d.get('stable_only_reference_metrics'):
            for key in ('stable_only_reference_metrics','provisional_reference_metrics'):
                row[key]={k:d[key][k] for k in ('wer','cer','word_errors','reference_words','character_errors','reference_characters','risk_flag_counts')}
            m=d['stable_only_reference_metrics'];mask=set(masks[sid]['excluded_selection_token_indices'])
            errors=sum(e['ref_index'] not in mask for e in m['word_edits'])
            row['checking_stable_lexical']={'word_errors':errors,'reference_words':masks[sid]['checking_words'],
                  'wer':errors/masks[sid]['checking_words'],'scope':'Projected deterministic alignment outside predeclared selection token masks; provisional reference, not clinical WER'}
            row['deletion_spans']=edit_spans(m['word_edits'],'D');row['insertion_spans']=edit_spans(m['word_edits'],'I')
            for flag in m['risk_flags']:
                alerts.append({'model':name,'sample':sid,'kind':'provisional_reference_alignment',**flag})
            # Preserve all edits, including morphology not covered by generic risk cues.
            save(path.parent.parent/('m4d_review_'+sid+'.json') if provenance=='M4-D measured' else out/('baseline_review_'+sid+'.json'),
                 {'result_path':str(path),'result_sha256':digest(path),'word_edits':m['word_edits'],
                  'risk_flags':m['risk_flags'],'clinical_wer':None})
        for adj in adjudications:
            source_sid='cardio_01' if 'cardio_01.' in adj['source'] else 'cardio_03'
            if sid!=source_sid:continue
            a,b=adj['acoustic_container_start_s'],adj['acoustic_container_end_s']
            stable=case_excerpt(d['commits'],a,b)
            previous=None;revisions=[];states=Counter();wrong_run=0;max_wrong_run=0
            for event in events:
                if event['type']!='update':continue
                text=case_excerpt(event['hypothesis'],a,b)
                if not text:continue
                if event['available_s']>=b:
                    state=phrase_status(adj['case'],text)
                    states[state['status']]+=1
                    wrong_run=wrong_run+1 if state['critical_conflict'] else 0
                    max_wrong_run=max(max_wrong_run,wrong_run)
                if previous and tokens(text)!=tokens(previous):
                    flags=sensitive_changes(previous,text)
                    if flags:revisions.append({'available_s':event['available_s'],'before':previous,'after':text,'categories':flags})
                previous=text
            case_rows.append({'model':name,'case':adj['case'],'sample':sid,'stable_excerpt':stable,
                'review':phrase_status(adj['case'],stable),'sensitive_hypothesis_revisions':revisions,
                'hypothesis_expression_states_after_clip_available':dict(states),
                'max_consecutive_critical_hypotheses_after_clip_available':max_wrong_run,
                'location_scope':'Candidate word timestamps overlap the independently fixed source clip container; timing locator only, not reference from model'})
            alerts.extend({'model':name,'sample':sid,'case':adj['case'],'kind':'hypothesis_revision_alert',**r} for r in revisions)
        key=(name,'full' if sid.startswith('cardio_') else 'yeti')
        bucket=pooled.setdefault(key,{'serial':[],'algorithmic':[],'inference':[]})
        for e in events:
            if e['type']!='update':continue
            bucket['inference'].append(e['inference_s'])
            for w in e['confirmed']:
                bucket['serial'].append(e['serial_completion_s']-w['end'])
                bucket['algorithmic'].append(e['available_s']-w['end'])
        results.append(row)
    aggregates=[]
    for (name,group),values in pooled.items():
        items=[r for r in results if r['model']==name and ('full' if r['sample'].startswith('cardio_') else 'yeti')==group]
        total=sum(r['audio_s'] for r in items)
        record={'model':name,'group':group,'files':len(items),'all_complete':complete_group(items,group),
                'audio_s':total,'rtf':sum(r['inference_rtf']*r['processed_s'] for r in items)/sum(r['processed_s'] for r in items),
                'serial_lag':distribution(values['serial']),'algorithmic_lag':distribution(values['algorithmic']),
                'inference_per_update':distribution(values['inference'])}
        if group=='full' and len(items)==3 and record['all_complete']:
            for label,key in (('stable','stable_only_reference_metrics'),('with_unconfirmed_tail','provisional_reference_metrics')):
                words=sum(r[key]['reference_words'] for r in items);errors=sum(r[key]['word_errors'] for r in items)
                chars=sum(r[key]['reference_characters'] for r in items);ce=sum(r[key]['character_errors'] for r in items)
                record[label]={'reference_words':words,'word_errors':errors,'wer':errors/words,
                               'reference_characters':chars,'character_errors':ce,'cer':ce/chars}
            words=sum(r['checking_stable_lexical']['reference_words'] for r in items)
            errors=sum(r['checking_stable_lexical']['word_errors'] for r in items)
            record['checking_stable']={'reference_words':words,'word_errors':errors,'wer':errors/words}
        aggregates.append(record)
    save(out/'incremental_comparison.json',{'results':results,'aggregates':aggregates,'clinical_wer':None})
    save(out/'incremental_case_review.json',case_rows)
    save(out/'sensitive_alerts.json',{'alerts':alerts,'policy':'Post-hoc alerts from recorded hypotheses/reference alignments, NOT automatic corrections or a validated clinical detector. Append-only confirmed output not changed.'})
    print(json.dumps({'offline_matrix_rows':len(rows),'incremental_results':len(results),'aggregates':aggregates,
                      'cases':[{k:r[k] for k in ('model','case','stable_excerpt','review')} for r in case_rows]},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','analyze']);p.add_argument('out');a=p.parse_args()
    out=Path(a.out)
    if a.action=='prepare':freeze_check_regions(out);source_provenance(out)
    else:analyze(out)
