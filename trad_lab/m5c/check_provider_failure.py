"""Fail real relay translations in-memory; transport EOF must not hide failure."""
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import patch
from trad_lab.m5b.memory import MemorySocket,MemoryHTTP,MemoryClosed,connector
from trad_lab.m5b.transport import Broker,TurboService
from trad_lab.m4c.incremental import Word
from trad_lab.m5c.runtime import SimulationProvider
from app.translation.engine import TranslationStatus


async def check(out):
    root=Path(__file__).resolve().parents[2];assert root.name=='copy'
    out=Path(out);out.mkdir(exist_ok=False,parents=True)
    key='c1-fault-test-only-12345678901234567890';(out/'test-key.txt').write_text(key)
    os.environ.update(M5B_BACKEND='turbo',M5B_SERVICE_KEY_FILE=str(out/'test-key.txt'),CAPTIONS_LOG_DIR=str(out/'logs'))
    from app.main import app
    from trad_lab.m5b import runtime
    import app.translation.engine as engine
    class Failure(SimulationProvider):
        async def translate(self,request):raise ValueError('Controlled invalid mock response')
    broker=Broker(lambda audio,start:[Word(' synthetic',0.,.5),Word(' confirmed.',.5,1.)],out/'backend')
    service=TurboService(broker,key);base='http://127.0.0.1:18010';messages=[]
    try:
      async with app.router.lifespan_context(app):
       async with MemoryHTTP(app,base_url=base) as http:
        owner=(await http.get('/api/operator/bootstrap')).json()['control_token']
        with patch.object(runtime,'network_connect',connector(service)),patch.object(engine,'provider_from_config',lambda cfg:(Failure(),TranslationStatus('ready','m5c-simulation','injected failure'))):
            socket=await MemorySocket(app,'/ws/session',query=b'direction=en-es',port=18010,headers=[(b'host',b'127.0.0.1:18010'),(b'origin',base.encode()),(b'sec-websocket-protocol',('operator.v1, '+owner).encode())],subprotocols=['operator.v1',owner]).open()
            credits=asyncio.Queue()
            async def consume():
                try:
                    while True:
                        m=json.loads(await socket.recv());messages.append(m)
                        if m.get('type')=='pcm_ack':await credits.put(m)
                except MemoryClosed:return
            task=asyncio.create_task(consume())
            while not any(m.get('type')=='config' for m in messages):await asyncio.sleep(.001)
            for _ in range(3):await socket.send(b'\x00\x00'*32000);await asyncio.wait_for(credits.get(),39)
            await socket.send(b'');await task;await socket.close()
            status=(await http.get('/api/operator/status',headers={'x-operator-token':owner})).json()
            failures=[m for m in messages if m.get('type')=='translation' and not m['translation']['success']]
            assert failures and not status['session_open'] and status['reliability']['outcome']=='incomplete'
            assert status['experimental_asr']['eof_observed'] and status['experimental_asr']['transport_completion']=='incomplete'
            summary=json.loads((out/'backend/session_0001/summary.json').read_text(encoding='utf-8'))
            assert summary['transport_complete'] and summary['produced_confirmed_words']>0
            assert app.state.caption_hub.last_caption is None
            record={'status':'PASS','checks':5,'backend_audio_transport_complete':True,'overall_completion':'incomplete','failed_translations':len(failures),'status_snapshot':status,'messages':messages}
            (out/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            ack=await http.post('/api/operator/acknowledge-stop',headers={'x-operator-token':owner,'origin':base},json={'session_id':status['session_id']})
            assert ack.status_code==200
            tail_socket=await MemorySocket(app,'/ws/session',query=b'direction=en-es',port=18010,headers=[(b'host',b'127.0.0.1:18010'),(b'origin',base.encode()),(b'sec-websocket-protocol',('operator.v1, '+owner).encode())],subprotocols=['operator.v1',owner]).open()
            tail_messages=[]
            async def tail_consume():
                try:
                    while True:tail_messages.append(json.loads(await tail_socket.recv()))
                except MemoryClosed:return
            task=asyncio.create_task(tail_consume())
            while not any(m.get('type')=='config' for m in tail_messages):await asyncio.sleep(.001)
            await tail_socket.send(b'\x00\x00'*32000)
            while not any(m.get('type')=='pcm_ack' for m in tail_messages):await asyncio.sleep(.001)
            await tail_socket.send(b'');await task;await tail_socket.close()
            tail_status=(await http.get('/api/operator/status',headers={'x-operator-token':owner})).json()
            assert tail_status['experimental_asr']['transcription_completion']=='unconfirmed_tail'
            assert not any(m.get('type')=='translation' for m in tail_messages)
            assert not tail_status['operator_history']['transcript']['confirmed_text']
            assert not any(e['message'].get('segmentation',{}).get('ready_segments') for e in tail_status['operator_history']['events'])
            assert app.state.caption_hub.last_caption is None and tail_status['reliability']['outcome']=='complete'
            (out/'tail_result.json').write_text(json.dumps({'status':'PASS','checks':4,'status_snapshot':tail_status,'messages':tail_messages},ensure_ascii=False,indent=2),encoding='utf-8')
    finally:broker.close()
    print('PASS: backend EOF complete, failed provider visible, overall incomplete, no caption publication')


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();asyncio.run(check(a.out))
