"""Integrity gates and observable latency; no unreviewed clinical WER.

Browser audio availability means delivery of a pre-resample block to the main
thread. It is not microphone ADC time or acoustic onset. DOM mutation and rAF
are observable render opportunities, not measured photons/projector latency.
"""
from bisect import bisect_left
import hashlib
import json
import math
from pathlib import Path
import statistics
import wave


def rows(path):
    with (Path(path)/'events.jsonl').open(encoding='utf-8') as f:
        for line in f: yield json.loads(line)


def verify_stream(path, kind):
    path=Path(path);summary=json.loads((path/'writer.json').read_text(encoding='utf-8'))
    if summary['failed']:raise ValueError('Evidence writer failed: '+summary['failed'])
    expected=summary['streams'].get(kind)
    if expected is None:raise ValueError('Missing stream: '+kind)
    file=path/(kind+('.f32le' if kind=='pre' else '.s16le'))
    offset=0;digest=hashlib.sha256();sequence=0;metadata=[]
    with file.open('rb') as f:
        for r in rows(path):
            if r['kind']!=kind:continue
            if r['seq']!=sequence or r['offset']!=offset:raise ValueError('Sequence/offset gap')
            block=f.read(r['bytes'])
            if len(block)!=r['bytes'] or hashlib.sha256(block).hexdigest()!=r['sha256']:raise ValueError('Block hash mismatch')
            sequence+=1;offset+=len(block);digest.update(block);metadata.append(r)
        if f.read(1):raise ValueError('Unlogged trailing bytes')
    if offset!=expected['bytes'] or digest.hexdigest()!=expected['sha256']:raise ValueError('Total hash mismatch')
    return expected,metadata


def validate_triplet(browser,trad,wlk):
    pre,p=verify_stream(browser,'pre');sent,s=verify_stream(browser,'sent')
    tr,t=verify_stream(trad,'received');wl,w=verify_stream(wlk,'received')
    if not sent['bytes']:raise ValueError('Empty PCM')
    if sent!=tr or sent!=wl:raise ValueError('CAPTURE/TRAD/WLK stream mismatch')
    # Verify individual message order, lengths and boundaries, including binary EOF.
    signatures=lambda data:[(r['bytes'],r['sha256']) for r in data]
    if signatures(s)!=signatures(t) or signatures(s)!=signatures(w):raise ValueError('Transport frame order/boundaries differ')
    if not s or s[-1]['bytes']!=0 or any(r['bytes']==0 for r in s[:-1]):raise ValueError('Exactly one terminal binary EOF required')
    rates={r['sample_rate'] for r in p}
    if len(rates)!=1 or next(iter(rates)) not in {16000,44100,48000}:raise ValueError('Unsupported/changing rate')
    if any(r['channels']!=1 for r in p):raise ValueError('Baseline expected mono input')
    if any(b['frame']!=a['frame']+a['samples'] for a,b in zip(p,p[1:])):raise ValueError('AudioWorklet frame discontinuity')
    if len(p)!=len(s)-1:raise ValueError('Original worker should yield exactly one sent block per pre block')
    if sum(r['samples']*4 for r in p)!=pre['bytes']:raise ValueError('Float sample count mismatch')
    return {'pre':pre,'sent':sent,'rate':next(iter(rates)),'pre_samples':pre['bytes']//4,
            'sent_samples':sent['bytes']//2,'blocks':len(p),'binary_eof':True,
            'three_way_sha256_equal':True},p,s


def clock_models(events):
    result={}
    for r in events:
        if r['kind']!='clock_bracket':continue
        v=r['page_clock'];page=v.get('state',{}).get('page') if v.get('state') else None
        if not page:continue
        lo,hi=r['py_before_ns']/1e6,r['py_after_ns']/1e6
        item={'offset_ms':(lo+hi)/2-v['now'],'uncertainty_ms':(hi-lo)/2,'browser_ms':v['now']}
        result.setdefault(page,[]).append(item)
    return result


def mapped(row,models):
    model=models.get(row.get('page'),[])
    if not model:return None
    # Nearest calibration; retain RTT bound, do not equate timeOrigin to QPC.
    c=min(model,key=lambda c:abs(c['browser_ms']-row['ms']))
    return row['ms']+c['offset_ms'],c['uncertainty_ms']


def percentile(values,p):
    if not values:return None
    values=sorted(values);x=(len(values)-1)*p;i=int(x);return values[i]+(values[min(i+1,len(values)-1)]-values[i])*(x-i)


def latency(events,pre,sent):
    from trad_lab.metrics import tokens
    models=clock_models(events); cumulative=[];n=0
    for r in sent:
        n+=r['bytes']//2;cumulative.append(n)
    ready=[];prefix=[]
    snapshots=[r for r in events if r['kind']=='browser_frame' and r['message'].get('type')=='asr']
    for r in events:
        if r['kind']!='ready':continue
        seg=r['segment'];end=seg.get('end_time');prefix+=tokens(seg['text'])
        item={'segment_id':seg['id'],'reason':seg['reason'],'end_audio_s':end,'metrics_ms':{},'uncertainty_ms':{}}
        if not isinstance(end,(int,float)) or not math.isfinite(end) or end<0:
            item['unavailable']='No valid audio-relative segment end';ready.append(item);continue
        index=bisect_left(cumulative,math.ceil(end*16000))
        if index>=len(pre):item['unavailable']='Audio timestamp outside captured samples';ready.append(item);continue
        origin=mapped(pre[index],models)
        if origin is None:item['unavailable']='No clock calibration';ready.append(item);continue
        def add(name,event):
            if event is None:return
            target=mapped(event,models)
            if target is None:return
            delta=target[0]-origin[0];uncertainty=target[1]+origin[1]
            # A confirmed segment before its reported end is an inconsistent
            # timestamp/mapping; never turn it into a plausible zero latency.
            if delta < -uncertainty:item.setdefault('inconsistent',[]).append(name);return
            item['metrics_ms'][name]=delta;item['uncertainty_ms'][name]=uncertainty
        add('ready_received',r)
        # Exact cumulative prefix prevents common words matching a wrong segment.
        hypotheses=[];confirmed=[]
        for snap in snapshots:
            state=snap['message'].get('transcript',{});c=tokens(state.get('confirmed_text',''))
            h=tokens(state.get('confirmed_text','')+' '+state.get('partial_text',''))
            if h[:len(prefix)]==prefix:hypotheses.append(snap)
            if c[:len(prefix)]==prefix:confirmed.append(snap)
        add('first_full_segment_hypothesis_received',hypotheses[0] if hypotheses else None)
        add('raw_confirmed_received',confirmed[0] if confirmed else None)
        matching=[x for x in events if x['kind']=='dom' and x.get('element')=='ready' and '['+seg['id']+']' in x.get('text','')]
        add('operator_ready_dom',next((x for x in matching if x['page']!=r['page']),None))
        add('capture_ready_dom',next((x for x in matching if x['page']==r['page']),None))
        add('diagnostic_overlay_dom',next((x for x in events if x['kind']=='overlay_dom' and x['segment_id']==seg['id']),None))
        add('diagnostic_overlay_raf',next((x for x in events if x['kind']=='overlay_paint_opportunity' and x['segment_id']==seg['id'] and x.get('visibility')=='visible'),None))
        ready.append(item)
    stages={key:{'n':len(v),'median_ms':statistics.median(v),'p95_ms':percentile(v,.95)}
            for key in {k for x in ready for k in x['metrics_ms']}
            if (v:=[x['metrics_ms'][key] for x in ready if key in x['metrics_ms']])}
    eof=next((r for r in events if r['kind']=='binary_eof'),None)
    terminal=next((r for r in events if r['kind']=='terminal_observed'),None)
    drain=None
    if eof and terminal and mapped(eof,models) and mapped(terminal,models):
        a,b=mapped(eof,models),mapped(terminal,models);drain={'ms':b[0]-a[0],'uncertainty_ms':a[1]+b[1]}
    global_first={}
    if pre:
        origin=mapped(pre[0],models)
        for label,condition in [('first_hypothesis_from_capture_start',lambda s: bool(s.get('partial_text') or s.get('confirmed_text'))),
                                ('first_confirmation_from_capture_start',lambda s: bool(s.get('confirmed_text')))]:
            event=next((r for r in snapshots if condition(r['message'].get('transcript',{}))),None)
            target=mapped(event,models) if event else None
            if origin and target:global_first[label]={'ms':target[0]-origin[0],'uncertainty_ms':origin[1]+target[1],
                'caution':'Includes acoustic preroll; not voice-onset latency'}
    return {'segments':ready,'summary':stages,'flush_drain':drain,'first_events':global_first,'clock_calibrations':models,
        'origin':'Main-thread availability of the input block associated with the transmitted sample at segment end; original-worker one-to-one mapping only',
        'scope':'Browser reception/DOM/rAF opportunities, not ADC/acoustic/physical display or Spanish translation latency',
        'limits':'Clock RTT bounds exclude undetected audio-stack buffering and between-calibration drift. Missing mappings stay unavailable.'}


def analyze(capture,trad,wlk):
    capture=Path(capture);browser=capture/'browser'
    control=json.loads((capture/'completion.json').read_text(encoding='utf-8'))
    owner=control.get('owner') or {}
    if not owner.get('owns_session') or owner.get('session_open') or owner.get('outcome')!='complete':
        raise ValueError('Owner STOP/closed/complete contract not verified')
    integrity,pre,sent=validate_triplet(browser,trad,wlk)
    import numpy as np
    original=np.fromfile(browser/'pre.f32le',dtype='<f4')
    if not np.all(np.isfinite(original)):raise ValueError('Nonfinite captured input')
    integrity['signal']={'rms':float(np.sqrt(np.mean(original.astype('float64')**2))),
        'peak':float(np.max(np.abs(original))),'full_scale_samples':int(np.count_nonzero(np.abs(original)>=1)),
        'caution':'Browser mono float after OS/track processing, before CAPTURE resampling; not raw ADC'}
    events=list(rows(browser));terminal=[r for r in events if r['kind']=='terminal_observed']
    if not terminal or terminal[-1].get('outcome')!='complete':raise ValueError('Complete owner STOP required')
    frames=[{'at':r['ms']/1000,'message':r['message']} for r in events if r['kind']=='browser_frame']
    from trad_lab.streaming import analyze_capture
    text=analyze_capture(frames,reference=None)
    wav=capture/'sent_pcm.wav'
    if wav.exists():raise FileExistsError('Do not overwrite analysis WAV')
    with wave.open(str(wav),'wb') as f:
        f.setparams((1,2,16000,0,'NONE','not compressed'))
        with (browser/'sent.s16le').open('rb') as source:
            for block in iter(lambda:source.read(1048576),b''):f.writeframesraw(block)
    # Listening derivative only; exact original f32 remains authoritative.
    prewav=capture/'pre_listening_s16.wav'
    if prewav.exists():raise FileExistsError('Do not overwrite pre-resample listening WAV')
    quantized=(np.clip(original,-1,1)*np.where(original<0,32768,32767)).astype('<i2')
    with wave.open(str(prewav),'wb') as f:
        f.setparams((1,2,integrity['rate'],0,'NONE','not compressed'));f.writeframes(quantized.tobytes())
    result={'integrity':integrity,'text':text,'latency':latency(events,pre,sent),
            'clinical_wer':None,'reference_gate':'Review exact acoustic/MP3 boundaries and TXT before scoring',
            'source_playback':[r for r in events if r['kind'].startswith('reference_')]}
    out=capture/'analysis.json'
    with out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,ensure_ascii=False)
    return out
