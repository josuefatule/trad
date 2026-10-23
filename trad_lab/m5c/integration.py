"""Real TRAD and Turbo ASGI routes, no TCP. Recorded or native decoder explicit."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import time
from unittest.mock import patch
import wave
from trad_lab.audio import digest
from trad_lab.m4c.incremental import Word
from trad_lab.m5b.memory import MemorySocket,MemoryHTTP,MemoryClosed,connector
from trad_lab.m5b.transport import Broker,TurboService
from trad_lab.m5a.consumer import compact

ROOT=Path(__file__).resolve().parents[2]
WORKSPACE=Path('C:/live-captions')
BASE=WORKSPACE/'logs/trad_lab/m5a_20261020T201327Z/gpu_r1/turbo'


async def check(out,mode):
    assert ROOT.name=='copy' and ROOT.is_relative_to(WORKSPACE/'logs/trad_lab')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    key='test-only-c1-memory-key-not-production-1234567890'
    (out/'test-key.txt').write_text(key,encoding='utf-8')
    os.environ.update(M5B_BACKEND='turbo',M5B_SERVICE_KEY_FILE=str(out/'test-key.txt'),CAPTIONS_LOG_DIR=str(out/'operational_logs'))
    from app.main import app
    from trad_lab.m5b import runtime
    from trad_lab.m5c import runtime as c1
    active={};control=0;native=None;native_calls=0
    if mode=='gpu':
        from trad_lab.m5b.model import load_decoder
        from trad_lab.m4c.replay import ClosedServices
        guard=ClosedServices();assert guard.check()['safe'], 'All services must remain closed'
        native=load_decoder(out/'model_runtime')
    def decode(audio,start):
        nonlocal control,native_calls
        if mode=='control':
            event=active['updates'][control];control+=1
            assert event['window_start_sample']==round(start*16000)
            assert hashlib.sha256(audio.astype('<f4').tobytes()).hexdigest()==event['window_f32_sha256']
            return [Word(**w) for w in event['decoder_words']]
        if native_calls%32==0:assert guard.check()['safe']
        native_calls+=1
        return native(audio,start)
    broker=Broker(decode,out/'backend');service=TurboService(broker,key)
    base='http://127.0.0.1:18010';comparisons=[]
    # Independent hard guards: no real provider HTTP, microphone APIs or TCP paths.
    def no_http(*a,**k):raise AssertionError('Real HTTP forbidden in C1')
    import app.translation.providers as providers
    try:
      with patch.object(providers,'urlopen',no_http):
       async with app.router.lifespan_context(app):
        async with MemoryHTTP(app,base_url=base) as http:
         owner_info=(await http.get('/api/operator/bootstrap')).json();owner=owner_info['control_token']
         def headers(token=None):return {'x-operator-token':token or owner,'origin':base}
         assert (await http.get('/m5c/capabilities')).json()['physical_enabled'] is False
         with patch.object(runtime,'network_connect',connector(service)):
          for name in ('yeti_received_full','cardio_01'):
            if mode=='gpu':assert guard.check()['safe']
            started=time.perf_counter();baseline_path=BASE/name/'result.json'
            baseline=json.loads(baseline_path.read_text(encoding='utf-8'))
            active=json.loads(baseline_path.read_text(encoding='utf-8'));active['updates']=[json.loads(x) for x in baseline_path.with_name('events.jsonl').read_text(encoding='utf-8').splitlines() if json.loads(x)['type']=='update'];control=0
            src=Path(baseline['sample']['path']);assert digest(src)==baseline['sample']['sha256']
            if src.suffix=='.s16le':pcm=src.read_bytes()
            else:
                with wave.open(str(src),'rb') as w:
                    assert (w.getnchannels(),w.getsampwidth(),w.getframerate())==(1,2,16000);pcm=w.readframes(w.getnframes())
            folder=out/name;folder.mkdir()
            overlay=await MemorySocket(app,'/ws/overlay',port=18010,headers=[(b'host',b'127.0.0.1:18010')]).open()
            overlay_events=[]
            async def consume_overlay():
                try:
                    while True:overlay_events.append(json.loads(await overlay.recv()))
                except MemoryClosed:return
            overlay_task=asyncio.create_task(consume_overlay())
            socket=await MemorySocket(app,'/ws/session',query=b'direction=en-es',port=18010,
                headers=[(b'host',b'127.0.0.1:18010'),(b'origin',base.encode()),(b'sec-websocket-protocol',('operator.v1, '+owner).encode())],subprotocols=['operator.v1',owner]).open()
            events=[];ready=[];translations=[];last_lines=[];credits=asyncio.Queue();terminals=[]
            while True:
                item=json.loads(await socket.recv());events.append(item)
                if item.get('type')=='error':raise AssertionError(item)
                if item.get('type')=='config':
                    sid=item['session_id'];assert item['translation_status']['provider']=='m5c-simulation'
                    assert item['direction']['id']=='en-es' and item['normalization_mode']=='identity';break
            async def consume():
                nonlocal last_lines
                try:
                    while True:
                        item=json.loads(await socket.recv());events.append(item)
                        assert item.get('type')!='error',item
                        payload=item.get('payload',{})
                        if 'lines' in payload:
                            assert payload['lines'][:len(last_lines)]==last_lines;last_lines=payload['lines']
                        if item.get('type')=='pcm_ack':await credits.put(item)
                        if item.get('type')=='translation':translations.append(item['translation'])
                        segmentation=item.get('segmentation')
                        if segmentation:
                            ready.extend(segmentation['ready_segments'])
                            assert compact(' '.join([*(s['text'] for s in ready),segmentation['pending_segment']]))==compact(segmentation['confirmed_text'])
                        if payload.get('type')=='ready_to_stop':terminals.append(payload)
                except MemoryClosed:return
            receiving=asyncio.create_task(consume());resumed=False;cleared=False;sent=0
            try:
              for sequence,offset in enumerate(range(0,len(pcm),64000)):
                block=pcm[offset:offset+64000];await socket.send(block)
                ack=await asyncio.wait_for(credits.get(),39);sent+=len(block)
                assert all(ack[k]==v for k,v in {'frame_sequence':sequence,'bytes':len(block),'received_bytes':sent,'sha256':hashlib.sha256(block).hexdigest(),'session_id':sid}.items())
                if not resumed and len(translations)>=2:
                    response=await http.post('/api/operator/resume',headers=headers(),json={'resume_secret':owner_info['resume_secret']})
                    assert response.status_code==200
                    previous=owner;owner_info=response.json();owner=owner_info['control_token'];assert owner!=previous
                    assert (await http.get('/api/operator/status',headers=headers(previous))).status_code==403
                    status=(await http.get('/api/operator/status',headers=headers())).json()
                    assert status['owns_session'] and status['session_open']
                    cleared_result=await http.post('/api/operator/clear',headers=headers(),json={'protocol_version':1,'session_id':sid,'visual_generation':status['visual_generation']})
                    assert cleared_result.status_code==200 and cleared_result.json()['applied'];resumed=cleared=True
              assert (await http.post('/api/operator/stop',headers=headers(),json={'session_id':sid})).status_code==200
              await socket.send(b'');await receiving;await socket.close()
              await asyncio.sleep(.01)
            finally:
              if not receiving.done():receiving.cancel();await asyncio.gather(receiving,return_exceptions=True)
              await overlay.close();await overlay_task
            status=(await http.get('/api/operator/status',headers=headers())).json()
            summary=json.loads((out/'backend'/f'session_{broker.serial:04d}'/'summary.json').read_text(encoding='utf-8'))
            raw=[json.loads(x) for x in (out/'backend'/f'session_{broker.serial:04d}'/'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            words=[w for e in raw for w in e.get('confirmed',[])];updates=[e for e in raw if e['type']=='update']
            assert words==baseline['commits'] and ''.join(w['text'] for w in words)==baseline['stable_text']
            expected_updates=active['updates']
            for actual,expected in zip(updates,expected_updates):
                for field in ('window_f32_sha256','decoder_words','hypothesis','confirmed','provisional','boundary_conflicts'):
                    assert actual[field]==expected[field],(name,field)
            assert len(updates)==len(expected_updates)
            assert summary['transport_complete'] and summary['received_bytes']==len(pcm) and summary['pcm_sha256']==hashlib.sha256(pcm).hexdigest()
            assert len(terminals)==1 and not status['session_open'] and status['reliability']['outcome']=='complete'
            assert len(ready)==len(translations) and len({r['id'] for r in ready})==len(ready)
            for seq,(r,t) in enumerate(zip(ready,translations),1):
                assert t['session_id']==sid and t['segment_id']==r['id'] and t['sequence']==seq
                assert t['success'] and (t['source_language'],t['target_language'])==('en','es')
                assert t['raw_text']==r['text']==t['normalized_text'] and t['translated_text']=='[SIMULACIÓN ES — NO CLÍNICA] '+r['text']
            captions=[e['caption'] for e in overlay_events if e['type']=='caption' and e['session_id']==sid]
            assert len(captions)==len(translations)
            assert [(c['sequence'],c['segment_id'],c['text']) for c in captions]==[(t['sequence'],t['segment_id'],t['translated_text']) for t in translations]
            assert all(c['target_language']=='es' for c in captions)
            assert resumed and cleared and any(e['type']=='captions_cleared' for e in overlay_events)
            assert not app.state.caption_hub.broadcast_errors
            for filename,data in [('front.json',events),('overlay.json',overlay_events)]:
                (folder/filename).write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
            result={'status':'PASS','sample':name,'mode':mode,'session_id':sid,'pcm_bytes':len(pcm),'pcm_sha256':summary['pcm_sha256'],
                'windows_exact':len(updates),'confirmed_records_exact':len(words),'ready':len(ready),'mock_translations':len(translations),'overlay_captions':len(captions),
                'confirmed_text_conserved':compact(' '.join(r['text'] for r in ready))==compact(baseline['stable_text']),
                'tail':terminals[0]['unconfirmed_eof_tail'],'owner_recovered':resumed,'clear_applied':cleared,'summary':summary,
                'wall_s':time.perf_counter()-started,'scope':'Actual TRAD/Turbo/translation/CaptionHub/overlay ASGI routes in memory; no TCP, browser rendering, native mic or DeepL.'}
            (folder/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8');comparisons.append(result)
            print(json.dumps({k:result[k] for k in ('status','sample','mode','pcm_bytes','confirmed_records_exact','mock_translations','overlay_captions')}),flush=True)
    finally:broker.close()
    (out/'comparison.json').write_text(json.dumps(comparisons,indent=2,ensure_ascii=False),encoding='utf-8')


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['control','gpu']);p.add_argument('--out',required=True);a=p.parse_args()
    asyncio.run(check(a.out,a.mode))
