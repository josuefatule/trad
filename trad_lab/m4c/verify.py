"""Independent audit of causal input windows and append-only output logs."""
import hashlib
import json
from pathlib import Path
import wave
import numpy as np
from trad_lab.audio import digest


def verify_result(path):
    path=Path(path);result=json.loads(path.read_text(encoding='utf-8'))
    sample=result['sample'];source=Path(sample['path'])
    if digest(source)!=sample['sha256']:raise ValueError('Source changed')
    if sample['format']=='wav':
        with wave.open(str(source),'rb') as f:
            if (f.getnchannels(),f.getsampwidth(),f.getframerate())!=(1,2,16000):raise ValueError('PCM format')
            raw=f.readframes(f.getnframes())
    else:raw=source.read_bytes()
    audio=np.frombuffer(raw,dtype='<i2').astype('float32')/32768.
    committed=[];last_received=0;updates=0;tail=[];eofs=0;overlap=[]
    for line in (path.parent/'events.jsonl').read_text(encoding='utf-8').splitlines():
        e=json.loads(line)
        if e['type']=='eof':
            eofs+=1;tail=e['unconfirmed_tail'];continue
        if e['type']!='update':continue
        start,end=e['window_start_sample'],e['window_end_sample']
        if not (0<=start<end<=len(audio) and end==e['received_samples'] and end>last_received):raise ValueError('Noncausal window bounds')
        cap=result['config']['max_buffer_s'] if result['config'].get('mode')=='adaptive' else result['config']['window_s']
        if end-start>round(cap*16000)+1:raise ValueError('Audio memory bound')
        expected=hashlib.sha256(audio[start:end].astype('<f4').tobytes()).hexdigest()
        if expected!=e['window_f32_sha256']:raise ValueError('Window PCM mismatch')
        for w in e['hypothesis']:
            if w['end']>end/16000+.05 or w['start']<start/16000-.05:raise ValueError('Timestamp outside available window')
        for w in e['confirmed']:
            if committed and w['start']<committed[-1]['end']-.08:
                overlap.append({'previous':committed[-1],'current':w,'call':e['call']})
            committed.append(w)
        last_received=end;updates+=1
    if ''.join(w['text'] for w in committed)!=result['stable_text']:raise ValueError('Confirmed output changed')
    if result['status']=='completed':
        if eofs!=1 or last_received!=len(audio):raise ValueError('Incomplete EOF')
        if result['eof_tail_text']!=''.join(w['text'] for w in tail):raise ValueError('EOF tail mismatch')
    return {'status':'PASS','result_status':result['status'],'source_sha256':sample['sha256'],
            'verified_windows':updates,'available_samples':last_received,'eofs':eofs,
            'confirmed_word_records':len(committed),'overlapping_commit_intervals':overlap,
            'scope':'Exact decoded window hashes and prefix availability; ASR timestamps are not independent acoustic ground truth'}


def replay_policy_compatibility(path):
    """Reconcile recorded decoder words again; never claim a new ASR timing run."""
    from .incremental import Config,Incremental,Word
    from .replay import pcm_reader
    path=Path(path);d=json.loads(path.read_text(encoding='utf-8'))
    if d['status']!='completed':raise ValueError('Complete source trace required')
    original=[json.loads(line) for line in (path.parent/'events.jsonl').read_text(encoding='utf-8').splitlines()]
    updates=[e for e in original if e['type']=='update'];index=0;compared=0
    def decode(audio,start):
        nonlocal index
        e=updates[index];index+=1
        if round(start*16000)!=e['window_start_sample'] or hashlib.sha256(audio.astype('<f4').tobytes()).hexdigest()!=e['window_f32_sha256']:
            raise ValueError('Changed decoder window under compatibility replay')
        return [Word(**w) for w in e.get('decoder_words',e['hypothesis'])]
    def sink(e):
        nonlocal compared
        if e['type']=='update':
            source=updates[compared];compared+=1
            if e['confirmed']!=source['confirmed'] or e['provisional']!=source['provisional']:
                raise ValueError('Policy output changed')
    engine=Incremental(decode,sink,Config(**d['config']))
    with pcm_reader(d['sample']) as (read,total):
        while True:
            raw=read(round(engine.config.update_s*16000))
            if not raw:break
            engine.push(np.frombuffer(raw,dtype='<i2').astype('float32')/32768.)
        engine.finish()
    if index!=len(updates):raise ValueError('Update count changed')
    return {'status':'PASS','source_result':str(path.resolve()),'source_sha256':digest(path),
            'windows':compared,'current_policy_sha256':digest(Path(__file__).with_name('incremental.py')),
            'scope':'Reconciliation/input-window equivalence using already recorded causal decoder words; no new inference or latency measurement'}
