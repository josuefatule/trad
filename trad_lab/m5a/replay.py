"""File-only, causal adapter/consumer replay. GPU and recorded-word controls."""
import argparse
import ctypes
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import time
import numpy as np
from trad_lab.audio import digest
from trad_lab.runner import DECODE, save
from trad_lab.metrics import metrics, tokens
from trad_lab.m4c.incremental import Word
from trad_lab.m4c.replay import datasets, pcm_reader, distribution
from trad_lab.m4d.evaluate import configure_runtime, caches, model_session
from .adapter import TurboAdapter, PROFILE
from .consumer import TradConsumer, compact

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT/'logs/trad_lab/m4d_20261020T192300Z/evaluation/incremental/large-v3-turbo/full'
OPTIONS = {**DECODE, 'vad_filter': True, 'initial_prompt': None, 'hotwords': None}


def memory_snapshot():
    """Windows process counters; no process enumeration or optional package."""
    class Counters(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(name,ctypes.c_size_t) for name in
            ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
             'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    c=Counters();c.cb=ctypes.sizeof(c)
    current=ctypes.windll.kernel32.GetCurrentProcess
    current.restype=ctypes.c_void_p
    query=ctypes.windll.psapi.GetProcessMemoryInfo
    query.argtypes=[ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong]
    query.restype=ctypes.c_int
    handle=current()
    if not query(handle,ctypes.byref(c),c.cb):
        raise OSError('Process memory counters unavailable')
    return {'working_set_mib':c.WorkingSetSize/1048576,'process_lifetime_peak_working_set_mib':c.PeakWorkingSetSize/1048576,
            'pagefile_mib':c.PagefileUsage/1048576}


def run(sample, out, model=None, monitor=None, baseline=None):
    out.mkdir(parents=True, exist_ok=False)
    source_events = []
    if baseline:
        old = json.loads(Path(baseline).read_text(encoding='utf-8'))
        if old['sample']['sha256'] != sample['sha256'] or old['config'] != asdict(PROFILE):
            raise ValueError('Wrong baseline input/profile')
        source_events = [json.loads(s) for s in Path(baseline).with_name('events.jsonl').read_text(encoding='utf-8').splitlines()]
    updates = [e for e in source_events if e['type'] == 'update']
    index = 0
    events, commits = [], []
    terminal_count = 0
    clock = 0.
    overhead, callback_s = [], []
    resources=[]
    max_payload_bytes=0
    with (out/'events.jsonl').open('w', encoding='utf-8') as raw_log, \
         (out/'asr.jsonl').open('w', encoding='utf-8') as asr_log, \
         (out/'segmentation.jsonl').open('w', encoding='utf-8') as seg_log:
        def seg_sink(event):
            seg_log.write(json.dumps(event, ensure_ascii=False)+'\n')
        consumer = TradConsumer(sample['id'], seg_sink)
        def raw_sink(event):
            nonlocal clock
            clock = (updates[event['call']-1]['serial_completion_s'] if baseline and event['type']=='update'
                     else event.get('serial_completion_s', clock))
            events.append(event)
            if not baseline:resources.append({'call':event.get('call'),'cpu_s':time.process_time(),**memory_snapshot()})
            commits.extend(event.get('confirmed', []))
            raw_log.write(json.dumps(event, ensure_ascii=False)+'\n')
        def emit(payload):
            nonlocal terminal_count,max_payload_bytes
            started = time.perf_counter()
            terminal_count += int(payload.get('type')=='ready_to_stop')
            encoded=json.dumps(payload, ensure_ascii=False)
            max_payload_bytes=max(max_payload_bytes,len(encoded.encode('utf-8')))
            asr_log.write(encoded+'\n')
            consumer.receive(payload, clock)
            callback_s.append(time.perf_counter()-started)
        def decode(audio, start):
            nonlocal index
            if baseline:
                event = updates[index]
                index += 1
                if round(start*16000) != event['window_start_sample'] or hashlib.sha256(audio.astype('<f4').tobytes()).hexdigest() != event['window_f32_sha256']:
                    raise ValueError('Adapter changed canonical baseline audio window')
                return [Word(**w) for w in event['decoder_words']]
            monitor.check()
            segments, info = model.transcribe(audio, **OPTIONS)
            words = [Word(w.word, start+w.start, start+w.end, w.probability)
                     for s in segments for w in s.words or []]
            monitor.check()
            return words
        adapter = TurboAdapter(sample['id'], decode, emit, raw_sink=raw_sink, backend='turbo-experimental')
        started = time.perf_counter()
        adapter.start()
        pcm_hash = hashlib.sha256()
        sequence = 0
        try:
            with pcm_reader(sample) as (read, total):
                while True:
                    # Original physical wire message size; corpus in canonical 2 s chunks.
                    block = read(43 if sample['format']=='s16le' else 32000)
                    if not block:
                        break
                    pcm_hash.update(block)
                    before = time.perf_counter()
                    compute_before = adapter.engine.compute_s
                    adapter.push(sample['id'], sequence, block)
                    overhead.append(time.perf_counter()-before-(adapter.engine.compute_s-compute_before))
                    sequence += 1
                adapter.request_stop(sample['id'])
                stats = adapter.push(sample['id'], sequence, b'')
            if baseline:
                if index != len(updates):
                    raise ValueError('Baseline update count changed')
                fresh = [e for e in events if e['type']=='update']
                if any(a['confirmed']!=b['confirmed'] or a['provisional']!=b['provisional'] for a,b in zip(fresh,updates)):
                    raise ValueError('Adapter changed baseline policy output')
            if adapter.pcm_sha.hexdigest()!=pcm_hash.hexdigest() or adapter.received_bytes!=total*2:
                raise ValueError('PCM reception integrity mismatch')
            stable = ''.join(w['text'] for w in commits)
            ready = ' '.join(s.text for s in consumer.ready)
            if compact(stable)!=compact(consumer.state.confirmed_text) or compact(stable)!=compact(ready):
                raise ValueError('Consumer introduced text difference')
            tail = ''.join(w['text'] for w in adapter.tail)
            if baseline and (stable!=old['stable_text'] or tail!=old['eof_tail_text']):
                raise ValueError('Baseline final text/EOF tail changed')
        except Exception as exc:
            save(out/'abort.json', {'error_type':type(exc).__name__, 'message':str(exc),
                 'received_bytes':adapter.received_bytes, 'automatic_retry':False})
            raise
        elapsed = time.perf_counter()-started
    lag = [e['serial_completion_s']-w['end'] for e in events for w in e.get('confirmed',[])]
    ready_delay = [s.latency_ms/1000 for s in consumer.ready]
    result = {'status':'completed', 'sample':sample, 'config':asdict(PROFILE), 'decoding':OPTIONS,
              'backend':'turbo-experimental', 'recorded_word_control':bool(baseline),
              'baseline_path':str(baseline) if baseline else None,
              'baseline_sha256':digest(baseline) if baseline else None,
              'stats':stats, 'audio_s':total/16000, 'processed_s':total/16000,
              'replay_wall_s':elapsed, 'inference_rtf':adapter.engine.compute_s/(total/16000),
              'stable_text':stable, 'eof_tail_text':tail, 'final_text_with_unconfirmed_eof_tail':stable+tail,
              'commits':commits, 'ready_text':ready, 'ready_segments':[asdict(s) for s in consumer.ready],
              'serial_confirmation_lag_s':distribution(lag) if not baseline else None,
              'ready_delay_after_first_confirmed_source_s':distribution(ready_delay),
              'consumer_callback_s':distribution(callback_s), 'nondecoder_push_s':distribution(overhead),
              'input_messages':sequence, 'received_bytes':adapter.received_bytes,
              'received_pcm_sha256':adapter.pcm_sha.hexdigest(),
              'terminal_count':terminal_count,
              'integration_errors':[], 'confirmed_to_ready_exact_whitespace_normalized':True,
              'confirmed_snapshot_prefix_immutable':True,
              'tail_separate_and_not_in_ready':True,
              'peak_audio_samples':adapter.engine.peak_samples, 'peak_word_state':adapter.engine.peak_words,
              'calls':adapter.engine.calls, 'snapshot_sources':len(adapter.lines),
              'max_asr_payload_bytes':max_payload_bytes,
              'timing_scope':'Accelerated serial replay: availability sample index, measured decoder duration, simulated 100 ms SegmentManager ticks. No network/DOM/translation/acoustic timing. READY delay uses first seen confirmed source, not speech onset. Control uses baseline clock and provides no new ASR timing.',
              'clear_scope':'Visual-only existing hub contract tested separately; no ASR reset'}
    if sample.get('reference') is not None:
        result['stable_only_reference_metrics']=metrics(sample['reference'],stable)
        result['provisional_reference_metrics']=metrics(sample['reference'],stable+tail)
    if sample.get('offline'):
        text=json.loads(Path(sample['offline']).read_text(encoding='utf-8'))['hypothesis_raw']
        result['offline_hypothesis_disagreement']=metrics(text,stable+tail)
    if sample.get('wlk'):
        text=json.loads(Path(sample['wlk']).read_text(encoding='utf-8'))['raw_before_segment_manager']
        result['wlk_hypothesis_disagreement']=metrics(text,stable+tail)
    save(out/'result.json', result)
    if resources:save(out/'process_resources.json',resources)
    print(json.dumps({'sample':sample['id'],'control':bool(baseline),'status':'PASS',
                     'calls':adapter.engine.calls, 'ready':len(consumer.ready), 'tail_words':len(tokens(tail)),
                     'wall_s':elapsed, 'integration_errors':0}), flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['control','gpu'])
    parser.add_argument('--out',required=True)
    parser.add_argument('--backend',choices=['turbo-experimental'],required=True)
    args=parser.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    for relative in ['trad_lab/m5a','trad_lab/m4c','trad_lab/m4d','app/captions']:
        target=out/'sources'/relative;target.mkdir(parents=True)
        for source in (ROOT/relative).glob('*.py'):
            shutil.copyfile(source,target/source.name)
    save(out/'source_hashes.json',{str(p.relative_to(out)):digest(p) for p in (out/'sources').rglob('*.py')})
    samples=datasets('yeti')+datasets('full')
    if args.action=='control':
        for sample in samples[1:]:
            run(sample,out/sample['id'],baseline=BASELINE/sample['id']/'result.json')
        return
    dll=configure_runtime()
    cache=caches(out)['large-v3-turbo']
    if cache['status']!='available':
        raise RuntimeError('Evaluated Turbo cache unavailable; no download')
    profile=json.loads((BASELINE/'profile.json').read_text(encoding='utf-8'))
    if asdict(PROFILE)!=profile['config'] or OPTIONS!=profile['decoding'] or digest(ROOT/'trad_lab/m4c/incremental.py')!=profile['engine_sha256']:
        raise ValueError('Frozen M4-D profile/engine changed')
    from faster_whisper.utils import get_assets_path
    if digest(Path(get_assets_path())/'silero_vad_v6.onnx')!=profile['vad_sha256']:
        raise ValueError('VAD model changed')
    save(out/'profile.json',profile)
    def work(model,monitor):
        for sample in samples:
            run(sample,out/'turbo'/sample['id'],model=model,monitor=monitor)
    model_session('large-v3-turbo',out/'runtime',cache,work)


if __name__=='__main__':
    main()
