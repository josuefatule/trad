"""In-memory full-app checks, invoked from a frozen copy in a fresh process."""
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import patch
from .memory import MemorySocket,MemoryClosed,connector,MemoryHTTP
from .transport import Broker,TurboService
from trad_lab.m4c.incremental import Word

ROOT=Path(__file__).resolve().parents[2]


async def check(out):
    if not ROOT.is_relative_to(Path('C:/live-captions/logs/trad_lab')) or ROOT.name!='copy':raise ValueError('Frozen copy required')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    os.environ.update(M5B_BACKEND='turbo',M5B_SERVICE_KEY_FILE=str(out/'test-key.txt'),CAPTIONS_LOG_DIR=str(out/'operational_logs'))
    key='in-memory-test-key-no-production-secret-123456789'
    (out/'test-key.txt').write_text(key,encoding='utf-8')
    from app.main import app
    from . import runtime
    calls=[]
    def decode(audio,start):
        calls.append(len(audio));return [Word(' untreated',0,.3),Word(' stage',.3,.5),Word(' two',.5,.7),Word(' hypertension.',.7,1.)]
    broker=Broker(decode,out/'backend');service=TurboService(broker,key)
    base='http://127.0.0.1:18010'
    async def drain(socket):
        messages=[]
        try:
            while True:messages.append(json.loads(await socket.recv()))
        except MemoryClosed:pass
        await socket.close();return messages
    async def open_front(token,query=b'direction=en-es',origin=base):
        return await MemorySocket(app,'/ws/session',query=query,port=18010,
             headers=[(b'host',b'127.0.0.1:18010'),(b'origin',origin.encode()),
                      (b'sec-websocket-protocol',('operator.v1, '+token).encode())],subprotocols=['operator.v1',token]).open()
    def h(token):return {'x-operator-token':token,'origin':base}
    checks={}
    try:
      async with app.router.lifespan_context(app):
       async with MemoryHTTP(app,base_url=base) as client:
        owner_info=(await client.get('/api/operator/bootstrap')).json();owner=owner_info['control_token']
        outsider=(await client.get('/api/operator/bootstrap')).json()['control_token']
        response=await client.get('/api/operator/status');assert response.status_code==403
        checks['diagnostics_require_operator_auth']=True
        with patch.object(runtime,'network_connect',connector(service)):
            for query,origin in [(b'direction=es-en',base),(b'direction=en-es','http://evil.example')]:
                try:await open_front(owner,query,origin)
                except MemoryClosed:pass
                else:raise AssertionError('Invalid direction/origin accepted')
            checks['english_only_and_origin']=True
            socket=await open_front(owner)
            messages=[]
            while True:
                item=json.loads(await socket.recv());messages.append(item)
                if item.get('type')=='config':break
            sid=messages[-1]['session_id']
            assert messages[-1]['translation_status']['state']=='disabled'
            assert messages[-1]['wlk']['backend']=='turbo-experimental'
            collecting=asyncio.create_task(drain(socket))
            await socket.send(b'0'*64000)
            for _ in range(200):
                if calls:break
                await asyncio.sleep(.005)
            assert calls
            body={'session_id':sid,'protocol_version':1,'visual_generation':0}
            assert (await client.post('/api/operator/stop',headers=h(outsider),json={'session_id':sid})).status_code==403
            assert (await client.post('/api/operator/clear',headers=h(outsider),json=body)).status_code==403
            competitor=await open_front(outsider);rejected=await drain(competitor)
            assert any(e.get('type')=='error' for e in rejected)
            assert broker.serial==1
            checks['one_owner_competing_start_rejected']=True
            before=len(calls)
            clear=await client.post('/api/operator/clear',headers=h(owner),json=body)
            assert clear.status_code==200 and clear.json()['applied']
            assert len(calls)==before
            assert (await client.post('/api/operator/clear',headers=h(owner),json=body)).status_code==409
            checks['clear_visual_only_stale_rejected']=True
            resumed=await client.post('/api/operator/resume',headers=h(owner),json={'resume_secret':owner_info['resume_secret']})
            assert resumed.status_code==200
            new_owner=resumed.json()['control_token']
            assert new_owner!=owner
            assert (await client.get('/api/operator/status',headers=h(owner))).status_code==403
            stop=await client.post('/api/operator/stop',headers=h(new_owner),json={'session_id':sid})
            assert stop.status_code==200 and stop.json()['requested']
            await socket.send(b'')
            messages+=await collecting
            status=(await client.get('/api/operator/status',headers=h(new_owner))).json()
            assert not status['session_open'] and status['state']=='stopped'
            diag=status['experimental_asr']
            assert diag['session_id']==sid and diag['transport_completion']=='complete'
            assert diag['transcription_completion']=='unconfirmed_tail'
            assert ''.join(w['text'] for w in diag['unconfirmed_eof_tail'])==' untreated stage two hypertension.'
            assert status['operator_history']['transcript']['confirmed_text']==''
            assert not any(e.get('segmentation',{}).get('ready_segments') for e in messages)
            assert any(e.get('type')=='operator_command' and e['command']=='stop' for e in messages)
            checks['owner_resume_stop_eof_and_tail_visible_after_recovery']=True
            second=await open_front(new_owner)
            second_messages=[]
            while True:
                item=json.loads(await second.recv());second_messages.append(item)
                if item.get('type')=='config':break
            second_id=second_messages[-1]['session_id'];assert second_id!=sid
            collect=asyncio.create_task(drain(second));await second.send(b'')
            second_messages+=await collect
            status=(await client.get('/api/operator/status',headers=h(new_owner))).json()
            assert status['experimental_asr']['session_id']==second_id
            assert status['experimental_asr']['unconfirmed_eof_tail']==[]
            assert broker.serial==2 and not broker.poisoned
            checks['second_session_isolated_no_duplicate_confirmation']=True
            assert all(m.get('type')!='translation' for m in messages+second_messages)
            checks['deepl_disabled_no_translation_events']=True
        # Explicit rollback in memory, after complete EOF/closure. No model swap
        # or fallback is performed: this is only the original WLK wire contract.
        class WLKWire:
            def __init__(self):
                self.queue=asyncio.Queue()
                self.queue.put_nowait(json.dumps({'type':'config','mode':'full','useAudioWorklet':True,
                    'session_language':'en','session_language_isolation':1}))
            async def recv(self):return await self.queue.get()
            async def send(self,pcm):
                assert not pcm
                self.queue.put_nowait(json.dumps({'type':'ready_to_stop'}))
            async def close(self):pass
        wire=WLKWire()
        async def wlk_connect(url,**kwargs):
            assert 'additional_headers' not in kwargs
            return wire
        os.environ['M5B_BACKEND']='wlk'
        with patch.object(runtime,'network_connect',wlk_connect):
            rollback=await open_front(new_owner)
            while True:
                item=json.loads(await rollback.recv())
                if item.get('type')=='config':break
            collect=asyncio.create_task(drain(rollback));await rollback.send(b'');await collect
            status=(await client.get('/api/operator/status',headers=h(new_owner))).json()
            assert status['experimental_asr']['backend']=='wlk'
            assert status['experimental_asr']['transcription_completion']=='not_reported_by_wlk'
            assert not status['session_open']
            checks['explicit_wlk_rollback_wire_contract_after_closure']=True
        (out/'result.json').write_text(json.dumps({'status':'PASS','checks':checks,'decoder_calls':len(calls),
          'scope':'Actual isolated app, authenticated Operator HTTP/WS and Turbo ASGI backend; all transport in memory. No TCP or microphone.'},indent=2),encoding='utf-8')
    finally:broker.close()
    print(json.dumps({'status':'PASS','checks':len(checks)}))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args()
    asyncio.run(check(args.out))
