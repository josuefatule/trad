"""Independent artifact checks and post-hoc clinical trace, never decoder input."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from trad_lab.audio import digest
from trad_lab.metrics import metrics, tokens
from trad_lab.runner import save
from trad_lab.m4c.replay import distribution
from trad_lab.m4c.replay import pcm_reader
from trad_lab.m4c.verify import verify_result
from trad_lab.m4d.analysis import phrase_status
from .consumer import compact
from .replay import BASELINE

CASES = [
    ('ORTHO','orthostatic hypotension','cardio_01',247,261,True),
    ('UNTREATED','untreated stage two hypertension','cardio_03',309,324,True),
    ('YEARS','four to six years','cardio_03',786,800,True),
    ('BP140','140 over 90','cardio_01',117,131,True),
    ('DRUG','spironolactone','cardio_03',576,590,False),
    ('ALDO','aldosterone','cardio_03',534,546,False),
    ('ASCVD','10-year ASCVD risk','cardio_03',740,755,False),
]


def rows(path):
    with Path(path).open(encoding='utf-8') as f:
        for line in f:
            yield json.loads(line)


def sampling_intervals(path):
    samples=list(rows(path))
    return distribution([b['at']-a['at'] for a,b in zip(samples,samples[1:])])


def audit(path):
    path=Path(path)
    result=json.loads(path.read_text(encoding='utf-8'))
    core=verify_result(path)
    import hashlib
    pcm_hash=hashlib.sha256()
    with pcm_reader(result['sample']) as (read,total):
        while True:
            block=read(32000)
            if not block:break
            pcm_hash.update(block)
    if result['received_bytes']!=total*2 or result['received_pcm_sha256']!=pcm_hash.hexdigest():
        raise ValueError('Adapter input differs from source PCM')
    engine=list(rows(path.with_name('events.jsonl')))
    updates=iter(e for e in engine if e['type']=='update')
    confirmed=[];previous=[];terminal=0;snapshots=0;last=None
    for sequence,p in enumerate(rows(path.with_name('asr.jsonl'))):
        if p.get('type')=='error' or p.get('error'):
            raise ValueError('Error in purported complete ASR trace')
        if p['adapter_sequence']!=sequence or p['session_id']!=result['sample']['id']:
            raise ValueError('ASR order/session mismatch')
        if sequence==0 and (p.get('type')!='config' or p.get('session_language')!='en' or p.get('session_language_isolation')!=1):
            raise ValueError('Missing language handshake')
        if terminal:raise ValueError('ASR event after terminal')
        if 'lines' in p:
            event=next(updates);snapshots+=1
            confirmed.extend(event['confirmed'])
            if p['lines'][:len(previous)]!=previous:
                raise ValueError('Confirmed source revised')
            previous=p['lines']
            flattened=[w for source in previous for w in source['words']]
            if flattened!=confirmed:
                raise ValueError('Word/timestamp mapping differs from engine')
            if any(source['text']!=''.join(w['text'] for w in source['words']) or
                   source['start']!=source['words'][0]['start'] or source['end']!=source['words'][-1]['end'] for source in previous):
                raise ValueError('Source text or bounds altered')
            if p['buffer_transcription']!=''.join(w['text'] for w in event['provisional']):
                raise ValueError('Provisional text altered')
            if p['buffer_diarization'] or p['buffer_translation']:
                raise ValueError('Invented diarization/translation')
        if p.get('type')=='ready_to_stop':
            terminal+=1
            if not p['audio_eof'] or p['pcm_sha256']!=result['received_pcm_sha256'] or p['received_bytes']!=result['received_bytes']:
                raise ValueError('Terminal PCM mismatch')
            if p['unconfirmed_eof_tail']!=engine[-1]['unconfirmed_tail']:
                raise ValueError('EOF tail changed')
        last=p
    if terminal!=1 or snapshots!=core['verified_windows']:
        raise ValueError('Missing snapshots/terminal')
    ready=[];ids=[];terminals=0
    for record in rows(path.with_name('segmentation.jsonl')):
        segmentation=record['segmentation']
        if any(e['type']=='late_revision_detected' for e in segmentation['events']):
            raise ValueError('Late revision introduced at segmentation')
        ready.extend(s['text'] for s in segmentation['ready_segments'])
        ids.extend(s['id'] for s in segmentation['ready_segments'])
        terminals+=int(record['phase']=='terminal')
        reconstructed=compact(' '.join([*ready,segmentation['pending_segment']]))
        if reconstructed!=compact(segmentation['confirmed_text']):
            raise ValueError('Intermediate READY/pending text loss or duplication')
    if len(ids)!=len(set(ids)) or compact(' '.join(ready))!=compact(result['stable_text']):
        raise ValueError('Final READY order/content/IDs mismatch')
    return {'core':core,'asr_snapshots':snapshots,'terminal_count':terminal,'ready_count':len(ready),
            'all_intermediate_segmentation_conserved':True,'immutable_word_records_and_timestamps':True,
            'tail_not_promoted':True,'result_sha256':digest(path),'scope':'New integration losses/duplicates only; inherited ASR errors and overlapping timestamps remain.'}


def excerpt(words,start,end):
    return ''.join(w['text'] for w in words if w['start']<end and w['end']>start)


def summarize(root):
    root=Path(root)
    results={p.parent.name:json.loads(p.read_text(encoding='utf-8')) for p in (root/'gpu_r1/turbo').glob('*/result.json')}
    if set(results)!={'yeti_received_full','cardio_01','cardio_02','cardio_03'}:
        raise ValueError('Four completed replays required; no partial aggregation')
    audits={}
    for group in ('control_final','gpu_r1/turbo'):
        for p in (root/group).glob('*/result.json'):
            audits[str(p.relative_to(root))]=audit(p)
    comparisons=[];clinical=[]
    for sample in ('cardio_01','cardio_02','cardio_03'):
        old=json.loads((BASELINE/sample/'result.json').read_text(encoding='utf-8'))
        new=results[sample]
        comparisons.append({'sample':sample,'baseline_result':str(BASELINE/sample/'result.json'),
            'baseline_result_sha256':digest(BASELINE/sample/'result.json'),
            'stable_text_exact':old['stable_text']==new['stable_text'],
            'eof_tail_exact':old['eof_tail_text']==new['eof_tail_text'],
            'word_records_exact':old['commits']==new['commits'],
            'stable_hypothesis_disagreement':metrics(old['stable_text'],new['stable_text']),
            'old_stable_lexical':old['stable_only_reference_metrics'],
            'new_stable_lexical':new['stable_only_reference_metrics'],
            'old_rtf':old['inference_rtf'],'new_rtf':new['inference_rtf']})
    for case,expression,sample,start,end,adjudicated in CASES:
        new=results[sample]
        old=json.loads((BASELINE/sample/'result.json').read_text(encoding='utf-8'))
        snippet=excerpt(new['commits'],start,end)
        before=excerpt(old['commits'],start,end)
        trace=[]
        for event in rows(root/'gpu_r1/turbo'/sample/'events.jsonl'):
            if event['type']!='update':continue
            hypothesis=[w for w in event['hypothesis'] if w['start']<end and w['end']>start]
            committed=[w for w in event['confirmed'] if w['start']<end and w['end']>start]
            if hypothesis or committed:
                trace.append({k:event[k] for k in ('call','available_s','window_start_sample','window_end_sample','window_f32_sha256') }|
                             {'hypothesis':hypothesis,'confirmed':committed,
                              'provisional':[w for w in event['provisional'] if w['start']<end and w['end']>start],
                              'boundary_conflicts':event['boundary_conflicts']})
        filename=root/'clinical_traces'/(case+'.json')
        save(filename,{'case':case,'priority_expression':expression,'sample':sample,
            'review_interval_s':[start,end],'alignment':'ASR-derived locator, not independent word alignment',
            'baseline_confirmed':before,'adapter_confirmed':snippet,'trace':trace,
            'review':phrase_status(case,snippet) if adjudicated else {'status':'unadjudicated medical discrepancy review; not automatically corrected'},
            'reference_used_by_decoder':False})
        clinical.append({'case':case,'expression':expression,'baseline':before,'adapter':snippet,
                         'trace':str(filename),'matches_baseline':before==snippet,
                         'review':phrase_status(case,snippet) if adjudicated else None})
    full=[results[k] for k in ('cardio_01','cardio_02','cardio_03')]
    aggregate={}
    for field in ('stable_only_reference_metrics','provisional_reference_metrics'):
        errors=sum(r[field]['word_errors'] for r in full)
        words=sum(r[field]['reference_words'] for r in full)
        chars=sum(r[field]['reference_characters'] for r in full)
        char_errors=sum(r[field]['character_errors'] for r in full)
        aggregate[field]={'errors':errors,'reference_words':words,'wer':errors/words,'character_errors':char_errors,'reference_characters':chars,'cer':char_errors/chars}
    def clocks(collection):
        events=[e for r in collection for e in rows(root/'gpu_r1/turbo'/r['sample']['id']/'events.jsonl') if e['type']=='update']
        return {'serial_confirmation_s':distribution([e['serial_completion_s']-w['end'] for e in events for w in e['confirmed']]),
                'algorithmic_confirmation_s':distribution([e['available_s']-w['end'] for e in events for w in e['confirmed']]),
                'decoder_update_s':distribution([e['inference_s'] for e in events]),
                'ready_after_confirmed_first_seen_s':distribution([s['latency_ms']/1000 for r in collection for s in r['ready_segments']]),
                'inference_rtf':sum(r['stats']['compute_s'] for r in collection)/sum(r['audio_s'] for r in collection)}
    resources=[x for r in results.values() for x in json.loads((root/'gpu_r1/turbo'/r['sample']['id']/'process_resources.json').read_text(encoding='utf-8'))]
    save(root/'integration_audit.json',audits)
    save(root/'baseline_comparison.json',comparisons)
    save(root/'clinical_review.json',clinical)
    save(root/'summary.json',{'aggregate':aggregate,'full_clocks':clocks(full),
        'yeti_clocks':clocks([results['yeti_received_full']]),
        'ready_count_full':sum(len(r['ready_segments']) for r in full),
        'process_peak_working_set_mib':max(x['process_lifetime_peak_working_set_mib'] for x in resources),
        'max_payload_bytes':max(r['max_asr_payload_bytes'] for r in results.values()),
        'gpu':json.loads((root/'gpu_r1/runtime/gpu_summary.json').read_text(encoding='utf-8')),
        'gpu_observed_sampling_intervals_s':sampling_intervals(root/'gpu_r1/runtime/gpu.jsonl'),
        'scope':'Four file replays; no microphone or services. Corpus reference provisional, Yeti hypothesis discrepancies only. Decoder clock excludes adapter/JSON overhead and browser/network/translation. No clinical certification.'})
    print(json.dumps({'verified_results':len(audits),'all_corpus_stable_exact':all(r['stable_text_exact'] for r in comparisons),
                      'clinical_cases':len(clinical),'aggregate':aggregate},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True)
    summarize(parser.parse_args().root)
