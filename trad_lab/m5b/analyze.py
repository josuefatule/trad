"""Independent PCM/window/snapshot audit after both in-memory hops close."""
import argparse
import hashlib
import json
from pathlib import Path
import wave
import numpy as np
from trad_lab.audio import digest
from trad_lab.m5a.consumer import compact
from trad_lab.m4c.replay import distribution


def rows(path):
    with Path(path).open(encoding='utf-8') as f:
        for line in f:yield json.loads(line)


def audit(result_path):
    result_path=Path(result_path);r=json.loads(result_path.read_text(encoding='utf-8'))
    source=r['source'];path=Path(source['path'])
    if digest(path)!=source['sha256']:raise ValueError('Input source changed')
    if source['format']=='wav':
        with wave.open(str(path),'rb') as f:pcm=f.readframes(f.getnframes())
    else:pcm=path.read_bytes()
    backend=Path(r['backend_evidence']);received=(backend/'received.s16le').read_bytes()
    if received!=pcm or hashlib.sha256(pcm).hexdigest()!=r['pcm_sha256']:raise ValueError('Transport PCM differs')
    offset=0;eof=0;frames=0
    for seq,frame in enumerate(rows(backend/'frames.jsonl')):
        if frame['sequence']!=seq or frame['offset']!=offset or eof:raise ValueError('Frame ordering/offset changed')
        block=pcm[offset:offset+frame['bytes']]
        if len(block)!=frame['bytes'] or hashlib.sha256(block).hexdigest()!=frame['sha256']:raise ValueError('Frame hash differs')
        offset+=frame['bytes'];eof+=int(frame['eof']);frames+=1
        if bool(frame['eof'])!=(frame['bytes']==0):raise ValueError('Invalid frame EOF')
    if eof!=1 or offset!=len(pcm):raise ValueError('Missing final PCM/EOF')
    audio=np.frombuffer(pcm,dtype='<i2').astype('float32')/32768.
    raw=list(rows(backend/'raw.jsonl'));updates=[];commits=[];last=0
    for event in raw:
        if event['type']!='update':continue
        start,end=event['window_start_sample'],event['window_end_sample']
        if not (0<=start<end<=len(audio) and end>last and end==event['received_samples'] and end-start<=480001):raise ValueError('Invalid causal window')
        if hashlib.sha256(audio[start:end].astype('<f4').tobytes()).hexdigest()!=event['window_f32_sha256']:raise ValueError('Canonical window changed')
        for w in event['hypothesis']:
            if not start/16000-.05<=w['start']<=w['end']<=end/16000+.05:raise ValueError('Timestamp outside source window')
        commits.extend(event['confirmed']);updates.append(event);last=end
    if raw[-1]['type']!='eof' or last!=len(audio):raise ValueError('Incomplete decoder EOF')
    tail=raw[-1]['unconfirmed_tail'];index=0;previous=[];terminal=0;sid=None
    for seq,payload in enumerate(rows(backend/'asr.jsonl')):
        if payload['adapter_sequence']!=seq:raise ValueError('ASR sequence differs')
        if sid is None:sid=payload['session_id']
        if payload['session_id']!=sid or terminal:raise ValueError('Session leak or postterminal event')
        if payload.get('type')=='error':raise ValueError('Error in supposedly complete replay')
        if 'lines' in payload:
            event=updates[index];index+=1
            if payload['lines'][:len(previous)]!=previous:raise ValueError('Immutable snapshot changed')
            previous=payload['lines']
            if [w for line in previous for w in line['words']]!=[w for e in updates[:index] for w in e['confirmed']]:raise ValueError('Word mapping altered')
            for line in previous:
                if line['text']!=''.join(w['text'] for w in line['words']) or line['start']!=line['words'][0]['start'] or line['end']!=line['words'][-1]['end']:raise ValueError('Source text/times altered')
            if payload['buffer_transcription']!=''.join(w['text'] for w in event['provisional']):raise ValueError('Provisional altered')
        if payload.get('type')=='ready_to_stop':
            terminal+=1
            if payload['unconfirmed_eof_tail']!=tail or not payload['audio_eof']:raise ValueError('EOF words altered')
    if index!=len(updates) or terminal!=1:raise ValueError('Missing snapshots/terminal')
    ready=[];ids=set();front_terminal=0;last_diagnostic=None
    for message in rows(result_path.with_name('operator.jsonl')):
        if message.get('session_id')!=sid or message.get('protocol_version')!=1:raise ValueError('Frontend session/protocol mismatch')
        if message.get('type') in ('error','translation'):raise ValueError('Unexpected error/translation')
        segment=message.get('segmentation')
        if segment:
            for item in segment['ready_segments']:
                if item['id'] in ids:raise ValueError('Duplicate READY')
                ids.add(item['id']);ready.append(item)
            if compact(' '.join([*(s['text'] for s in ready),segment['pending_segment']]))!=compact(segment['confirmed_text']):raise ValueError('Intermediate text loss/duplication')
            if any(e['type']=='late_revision_detected' for e in segment['events']):raise ValueError('New late revision')
        for normalized in message.get('normalization',{}).get('segments',[]):
            if normalized['raw_text']!=normalized['normalized_text'] or normalized['corrections'] or normalized['suggestions']:raise ValueError('Medical text changed by normalizer')
        payload=message.get('payload',{})
        if payload.get('type')=='ready_to_stop':
            front_terminal+=1
            if payload['unconfirmed_eof_tail']!=tail:raise ValueError('Frontend EOF tail hidden')
        if message.get('state')=='stopped':last_diagnostic=message.get('experimental_asr')
    if front_terminal!=1 or compact(' '.join(s['text'] for s in ready))!=compact(''.join(w['text'] for w in commits)):raise ValueError('Final frontend text differs')
    expected='unconfirmed_tail' if tail else 'all_emitted_words_confirmed'
    if not last_diagnostic or last_diagnostic['transport_completion']!='complete' or last_diagnostic['transcription_completion']!=expected:raise ValueError('Completion distinction missing')
    baseline=Path('C:/live-captions/logs/trad_lab/m5a_20261020T201327Z/gpu_r1/turbo')/r['sample']/'result.json'
    old=json.loads(baseline.read_text(encoding='utf-8'))
    if digest(baseline)!=r['baseline_sha256'] or commits!=old['commits'] or ''.join(w['text'] for w in tail)!=old['eof_tail_text']:raise ValueError('M5-A equivalence failed')
    return {'status':'PASS','result':str(result_path),'result_sha256':digest(result_path),'frames':frames,'pcm_bytes':len(pcm),
            'verified_windows':len(updates),'ready':len(ready),'backend_frontend_terminal_count':[terminal,front_terminal],
            'all_intermediate_text_conserved':True,'normalization_identity':True,'exact_M5A_words_timestamps_tail':True}


def summarize(root):
    root=Path(root);audits=[]
    for group in ('control_delivery','gpu_r1'):
        paths=list((root/group).glob('*/result.json'))
        if {p.parent.name for p in paths}!={'yeti_received_full','cardio_01','cardio_02','cardio_03'}:raise ValueError('Four complete samples required per group')
        audits.extend(audit(p) for p in paths)
    results=[json.loads(p.read_text(encoding='utf-8')) for p in (root/'gpu_r1').glob('*/result.json')]
    gpu=list(rows(root/'gpu_r1/gpu.jsonl'))
    resources=json.loads((root/'gpu_r1/process_resources.json').read_text(encoding='utf-8'))
    summary={'audited_results':len(audits),'verified_windows':sum(a['verified_windows'] for a in audits),
             'gpu_inferences':sum(r['calls'] for r in results),'gpu_ready':sum(len(r['ready']) for r in results),
             'max_outbox_bytes':max(r['transport_summary']['outbox_peak_bytes'] for r in results),
             'max_outbox_items':max(r['transport_summary']['outbox_peak_items'] for r in results),
             'gpu':json.loads((root/'gpu_r1/gpu_summary.json').read_text(encoding='utf-8')),
             'gpu_observed_interval_s':distribution([b['at']-a['at'] for a,b in zip(gpu,gpu[1:])]),
             'process_peak_working_set_mib':max(r['process_lifetime_peak_working_set_mib'] for r in resources),
             'confirmation_clock_scope':'Actual accelerated in-memory app timing; not physical/browser/network latency. SegmentManager ticks use wall time, unlike M5-A simulated serial ticks; READY partitions/counts are not expected identical.',
             'native_timeout_scope':'Quarantine, not termination of native CUDA call; no automatic retry',
             'clinical_scope':'Exact preservation of M5-A output, including known errors, not medical accuracy certification'}
    (root/'integration_audit.json').write_text(json.dumps(audits,indent=2),encoding='utf-8')
    (root/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    # Keep prior medical review/trace provenance without feeding it to ASR.
    prior=Path('C:/live-captions/logs/trad_lab/m5a_20261020T201327Z')
    clinical={'M5A_review':str(prior/'clinical_review.json'),'M5A_review_sha256':digest(prior/'clinical_review.json'),
              'outputs_exact':True,'no_automatic_corrections':True,
              'known_discrepancies':['140 over 90 → 140 over 19','aldosterone → eldest run','10-year ASCVD risk → tenure'],
              'late_revision_and_medication_provenance':str(prior/'clinical_traces'),
              'baseline_comparison':'All confirmed word records/timestamps and EOF tail exact for every sample; inherited late corrections/errors remain in RAW'}
    (root/'clinical_traceability.json').write_text(json.dumps(clinical,indent=2),encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);args=p.parse_args();summarize(args.root)
