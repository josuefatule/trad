"""Full B app and original provider with fake HTTP only. No model, TCP or mic."""
import asyncio,json,os
from pathlib import Path
from unittest.mock import patch
from trad_lab.m5c2b import runtime as b
from app.translation.providers import DeepLTranslatorProvider
from trad_lab.m5b.memory import MemoryHTTP,MemorySocket,MemoryClosed,connector
from trad_lab.m5b.transport import Broker,TurboService
from trad_lab.m4c.incremental import Word

async def check(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);key='test-local-backend-not-a-production-secret-123456789';(out/'test-key.txt').write_text(key)
    os.environ.update(M5B_BACKEND='turbo',CAPTIONS_LOG_DIR=str(out/'logs'),M5B_SERVICE_KEY_FILE=str(out/'test-key.txt'))
    bodies=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return json.dumps({'translations':[{'text':'Texto de prueba en español.'}]}).encode()
    def opener(request,timeout):
        body=json.loads(request.data);assert body['source_lang']=='EN' and body['target_lang']=='ES';bodies.append(body);return Response()
    def factory(key,url,timeout):return DeepLTranslatorProvider(key,url,timeout,opener=opener)
    with patch.object(b,'read_local_config',lambda:{'key':'test-fake-provider-key','url':'https://api-free.deepl.com/v2/translate'}),patch.object(b,'DeepLTranslatorProvider',factory):
      from app.main import app
      broker=Broker(lambda audio,start:[Word(' Experimental',0,.3),Word(' sample',.3,.6),Word(' sentence.',.6,1.)],out/'backend');service=TurboService(broker,key)
      from trad_lab.m5b import runtime as transport
      front=[];overlay=[];checks={}
      try:
       async with app.router.lifespan_context(app):
        async with MemoryHTTP(app) as http:
         token=(await http.get('/api/operator/bootstrap')).json()['control_token'];other=(await http.get('/api/operator/bootstrap')).json()['control_token'];base='http://127.0.0.1:18010'
         h={'x-operator-token':token,'origin':base}
         with patch.object(transport,'network_connect',connector(service)):
          ws=await MemorySocket(app,'/ws/session',query=b'direction=en-es',port=18010,headers=[(b'host',b'127.0.0.1:18010'),(b'origin',base.encode()),(b'sec-websocket-protocol',('operator.v1, '+token).encode())],subprotocols=['operator.v1',token]).open()
          while True:
            m=json.loads(await ws.recv());front.append(m)
            if m['type']=='config':break
          sid=m['session_id'];assert m['translation_status']['provider']=='deepl';assert m['experimental_transport']['pcm_credit']==1
          checks['explicit_english_credit_real_provider_configuration']=True
          sub=app.state.caption_hub.subscribe();acks=asyncio.Queue()
          async def drain():
            try:
             while True:
              m=json.loads(await ws.recv());front.append(m)
              if m['type']=='pcm_ack':acks.put_nowait(m)
            except MemoryClosed:pass
          task=asyncio.create_task(drain())
          for i in range(3):
            await ws.send(b'\0'*64000);assert (await asyncio.wait_for(acks.get(),5))['frame_sequence']==i
          status=(await http.get('/api/operator/status',headers=h)).json();generation=status['visual_generation']
          body={'session_id':sid,'visual_generation':generation,'hidden':True}
          assert (await http.post('/api/m5c/presentation',headers={'x-operator-token':other,'origin':base},json=body)).status_code==403
          assert (await http.post('/api/m5c/presentation',headers=h,json=body)).status_code==200
          body['visual_generation']=app.state.caption_hub.visual_generation;body['hidden']=False
          assert (await http.post('/api/m5c/presentation',headers=h,json=body)).status_code==200
          checks['authenticated_hold_resume']=True
          await ws.send(b'');await asyncio.wait_for(task,10);await ws.close()
          while not sub.queue.empty():overlay.append(sub.queue.get_nowait())
          app.state.caption_hub.unsubscribe(sub)
          status=(await http.get('/api/operator/status',headers=h)).json()
          assert status['state']=='stopped' and status['reliability']['outcome']=='complete'
          assert status['experimental_asr']['transport']['pending_confirmed_words']==0
          assert bodies and all(x['text']==['Experimental sample sentence.'] for x in bodies)
          translations=[m for m in front if m['type']=='translation'];assert len(translations)==1
          result=translations[0].get('result',translations[0].get('translation',{}))
          checks['original_http_body_english_spanish']=True;checks['normal_eof_and_zero_undelivered_words']=True
          assert any(m.get('type')=='caption' and m['caption']['target_language']=='es' and m['caption']['text']=='Texto de prueba en español.' for m in overlay)
          checks['original_caption_hub_spanish_caption']=True
          trace=(out/'logs/translation_trace.jsonl').read_text();assert 'test-fake-provider-key' not in trace and 'Authorization' not in trace
          checks['no_credentials_in_trace']=True
          assert not [m for m in overlay if m.get('type')=='caption' and m['caption']['text'].startswith('[MOCK')]
          (out/'result.json').write_text(json.dumps({'status':'PASS','checks':checks,'scope':'B app in memory with original DeepL HTTP adapter, response mocked. No real API or ASR inference','provider_calls':len(bodies)},indent=2))
          print(json.dumps({'status':'PASS','checks':len(checks),'provider_calls':len(bodies)}))
      finally:broker.close()
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();asyncio.run(check(a.out))
