"""File replay through the real isolated Operator app and ASGI Turbo backend.

Both WebSocket hops are bounded queues, never TCP. No browser/microphone here.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import wave
from unittest.mock import patch
from trad_lab.audio import digest
from trad_lab.m4c.incremental import Word
from trad_lab.m5a.consumer import compact
from .memory import MemoryHTTP,MemorySocket,MemoryClosed,connector
from .transport import Broker,TurboService

WORKSPACE=Path('C:/live-captions')
BASELINE=WORKSPACE/'logs/trad_lab/m5a_20261020T201327Z/gpu_r1/turbo'
ROOT=Path(__file__).resolve().parents[2]


async def replay(out,mode):
    if ROOT.name!='copy' or not ROOT.is_relative_to(WORKSPACE/'logs/trad_lab'):raise RuntimeError('Fresh isolated-copy process required')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    key='memory-only-replay-key-not-live-12345678901234567890'
    keyfile=out/'test-key.txt';keyfile.write_text(key,encoding='utf-8')
    os.environ.update(M5B_BACKEND='turbo',M5B_SERVICE_KEY_FILE=str(keyfile),CAPTIONS_LOG_DIR=str(out/'operational_logs'))
    from app.main import app
    from . import runtime
    current={};control_index=0;resources=[]
    monitor=None;native=None
    if mode=='gpu':
        from .model import load_decoder
        from trad_lab.m4.experiments import Monitor
        from trad_lab.m4c.replay import ClosedServices
        from trad_lab.m5a.replay import memory_snapshot
        monitor=Monitor(out/'gpu.jsonl');monitor.guard=ClosedServices();monitor.__enter__()
        native=load_decoder(out/'model_runtime')
    def decode(audio,start):
        nonlocal control_index
        if mode=='control':
            event=current['updates'][control_index];control_index+=1
            if round(start*16000)!=event['window_start_sample'] or hashlib.sha256(audio.astype('<f4').tobytes()).hexdigest()!=event['window_f32_sha256']:
                raise ValueError('Transport changed M5-A canonical decoder window')
            return [Word(**w) for w in event['decoder_words']]
        monitor.check();words=native(audio,start);monitor.check()
        resources.append({'sample':current['id'],'perf_counter_ns':time.perf_counter_ns(),'cpu_s':time.process_time(),**memory_snapshot()})
        return words
    broker=Broker(decode,out/'backend');service=TurboService(broker,key)
    comparisons=[]
    try:
      async with app.router.lifespan_context(app):
       async with MemoryHTTP(app) as client:
        owner=(await client.get('/api/operator/bootstrap')).json()['control_token']
        headers={'x-operator-token':owner,'origin':'http://127.0.0.1:18010'}
        with patch.object(runtime,'network_connect',connector(service)):
         for sample_id in ('yeti_received_full','cardio_01','cardio_02','cardio_03'):
            baseline_path=BASELINE/sample_id/'result.json'
            baseline=json.loads(baseline_path.read_text(encoding='utf-8'))
            current.clear();current.update(id=sample_id)
            if mode=='control':
                current['updates']=[json.loads(s) for s in baseline_path.with_name('events.jsonl').read_text(encoding='utf-8').splitlines() if json.loads(s)['type']=='update']
                control_index=0
            sample=baseline['sample'];source=Path(sample['path'])
            if digest(source)!=sample['sha256']:raise ValueError('Preserved source changed')
            if sample['format']=='wav':
                with wave.open(str(source),'rb') as f:
                    if (f.getnchannels(),f.getsampwidth(),f.getframerate())!=(1,2,16000):raise ValueError('PCM source format')
                    pcm=f.readframes(f.getnframes())
            else:pcm=source.read_bytes()
            folder=out/sample_id;folder.mkdir()
            started=time.perf_counter();ready=[];ready_ids=set();previous_lines=[];tail=None;terminal=0;error=None
            socket=await MemorySocket(app,'/ws/session',query=b'direction=en-es',port=18010,
                headers=[(b'host',b'127.0.0.1:18010'),(b'origin',b'http://127.0.0.1:18010'),
                         (b'sec-websocket-protocol',('operator.v1, '+owner).encode())],subprotocols=['operator.v1',owner]).open()
            operator_bytes=0
            with (folder/'operator.jsonl').open('w',encoding='utf-8') as log:
                async def consume():
                    nonlocal previous_lines,tail,terminal,error,operator_bytes
                    try:
                     while True:
                        raw=await socket.recv();operator_bytes+=len(raw.encode())
                        if operator_bytes>268435456:raise RuntimeError('Replay diagnostic budget')
                        log.write(raw+'\n');message=json.loads(raw)
                        if message.get('type')=='error':error=message;raise RuntimeError('Actual relay reported integration error')
                        payload=message.get('payload',{})
                        if 'lines' in payload:
                            if payload['lines'][:len(previous_lines)]!=previous_lines:raise ValueError('Confirmed prefix revised')
                            previous_lines=payload['lines']
                        segmentation=message.get('segmentation')
                        if segmentation:
                            if any(e['type']=='late_revision_detected' for e in segmentation.get('events',[])):raise ValueError('New late source revision')
                            for segment in segmentation['ready_segments']:
                                if segment['id'] in ready_ids:raise ValueError('Duplicate READY ID')
                                ready_ids.add(segment['id']);ready.append(segment)
                            if compact(' '.join([*(s['text'] for s in ready),segmentation['pending_segment']]))!=compact(segmentation['confirmed_text']):
                                raise ValueError('New READY/pending text loss or duplication')
                        if payload.get('type')=='ready_to_stop':tail=payload['unconfirmed_eof_tail'];terminal+=1
                    except MemoryClosed:return
                # Handshake must finish before any PCM is sent.
                while True:
                    raw=await socket.recv();log.write(raw+'\n');message=json.loads(raw)
                    if message.get('type')=='error':raise RuntimeError('Startup integration failure')
                    if message.get('type')=='config':
                        sid=message['session_id']
                        if message['translation_status']['state']!='disabled' or message['wlk']['backend']!='turbo-experimental':raise ValueError('Unexpected backend/translator')
                        break
                receiving=asyncio.create_task(consume())
                # File transport uses at most one canonical 2 s frame per credit.
                # The adapter's PCM partition invariance is tested separately.
                chunk=64000
                try:
                    for offset in range(0,len(pcm),chunk):
                        if receiving.done():receiving.result();raise RuntimeError('Early transport close')
                        await socket.send(pcm[offset:offset+chunk])
                    stop=await client.post('/api/operator/stop',headers=headers,json={'session_id':sid})
                    if stop.status_code!=200:raise ValueError('Owner STOP rejected')
                    await socket.send(b'')
                    await receiving;await socket.close()
                finally:
                    if not receiving.done():receiving.cancel();await asyncio.gather(receiving,return_exceptions=True)
            status=(await client.get('/api/operator/status',headers=headers)).json()
            backend=out/'backend'/f'session_{broker.serial:04d}'
            summary=json.loads((backend/'summary.json').read_text(encoding='utf-8'))
            events=[json.loads(s) for s in (backend/'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            commits=[w for event in events for w in event.get('confirmed',[])]
            stable=''.join(w['text'] for w in commits)
            if terminal!=1 or tail is None or not summary['transport_complete'] or status['session_open']:
                raise ValueError('Incomplete transport/EOF/closure')
            if hashlib.sha256(pcm).hexdigest()!=summary['pcm_sha256'] or summary['received_bytes']!=len(pcm):raise ValueError('PCM integrity failure')
            if compact(stable)!=compact(' '.join(s['text'] for s in ready)):raise ValueError('Final READY differs')
            record={'sample':sample_id,'mode':mode,'baseline_sha256':digest(baseline_path),'source':sample,
                'status':'PASS','pcm_sha256':summary['pcm_sha256'],'received_bytes':len(pcm),
                'stable_text':stable,'eof_tail_text':''.join(w['text'] for w in tail),'commits':commits,
                'stable_text_exact':stable==baseline['stable_text'],'word_records_exact':commits==baseline['commits'],
                'eof_tail_exact':tail==[json.loads(s) for s in baseline_path.with_name('events.jsonl').read_text(encoding='utf-8').splitlines()][-1]['unconfirmed_tail'],
                'ready':ready,'new_integration_errors':0,'terminal_count':terminal,'transport_summary':summary,
                'diagnostics':status['experimental_asr'],'calls':sum(e['type']=='update' for e in events),
                'wall_s':time.perf_counter()-started,'backend_evidence':str(backend),
                'scope':'Actual authenticated TRAD routes and Turbo service via bounded in-memory ASGI hops; no TCP/browser/microphone/physical latency measurement'}
            if not all(record[k] for k in ('stable_text_exact','word_records_exact','eof_tail_exact')):raise ValueError('ASR differs from M5-A; stop batch without tuning')
            if mode=='control' and control_index!=len(current['updates']):raise ValueError('Control update count changed')
            (folder/'result.json').write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8')
            comparisons.append({k:record[k] for k in ('sample','status','calls','received_bytes','stable_text_exact','word_records_exact','eof_tail_exact','wall_s')})
            print(json.dumps(comparisons[-1]),flush=True)
    finally:
        broker.close()
        if monitor:monitor.__exit__(None,None,None)
    (out/'comparison.json').write_text(json.dumps(comparisons,indent=2),encoding='utf-8')
    if resources:(out/'process_resources.json').write_text(json.dumps(resources,indent=2),encoding='utf-8')
    if monitor:
        (out/'gpu_summary.json').write_text(json.dumps({'samples':len(monitor.samples),
            'peak_used_mib':max(float(s['used_mib']) for s in monitor.samples),'min_free_mib':min(float(s['free_mib']) for s in monitor.samples),
            'max_temperature_c':max(float(s['temperature_c']) for s in monitor.samples)},indent=2),encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['control','gpu']);p.add_argument('--out',required=True)
    args=p.parse_args();asyncio.run(replay(args.out,args.mode))
