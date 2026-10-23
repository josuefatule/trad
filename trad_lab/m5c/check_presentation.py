"""Exercise the copy-only authenticated hold gate, not a substitute renderer."""
import asyncio
import json
import os
from pathlib import Path
from app.translation.engine import TranslationEngine,TranslationConfig
from trad_lab.m5c.runtime import SimulationProvider
from trad_lab.m5b.memory import MemoryHTTP


async def check(out):
    root=Path(__file__).resolve().parents[2];assert root.name=='copy'
    out=Path(out);out.mkdir(exist_ok=False,parents=True);os.environ['CAPTIONS_LOG_DIR']=str(out/'logs')
    from app.main import app
    hub=app.state.caption_hub;authority=app.state.operator_authority
    owner=authority.issue();outsider=authority.issue();authority.owner=owner
    hub.begin('presentation-test',direction={'id':'en-es','source_language':'en','target_language':'es'});hub.set_state(hub.session_id,'live')
    base='http://127.0.0.1:18010';events=[];results=[]
    subscriber=hub.subscribe()
    async def collect(r,s):results.append(r);hub.publish(r)
    engine=TranslationEngine(TranslationConfig(enabled=True,provider='mock',source_language='en',target_language='es'),SimulationProvider(),hub.session_id,collect)
    await engine.start()
    def h(t=owner):return {'x-operator-token':t,'origin':base}
    body=lambda hidden:{'session_id':hub.session_id,'hidden':hidden,'visual_generation':hub.visual_generation}
    try:
      async with MemoryHTTP(app,base_url=base) as http:
        await engine.submit('one','first','first');await engine.wait_idle();assert hub.last_caption
        assert (await http.post('/api/m5c/presentation',headers=h(outsider),json=body(True))).status_code==403
        assert (await http.post('/api/m5c/presentation',headers=h(),json=body(True))).status_code==200
        assert hub.last_caption is None and hub._m5c_hidden
        await engine.submit('two','140 over 19','140 over 19');await engine.wait_idle()
        assert hub.last_caption is None and hub.sequence==2 and len(results)==2
        stale={**body(False),'visual_generation':0}
        assert (await http.post('/api/m5c/presentation',headers=h(),json=stale)).status_code==409
        assert (await http.post('/api/m5c/presentation',headers=h(),json=body(False))).status_code==200
        assert hub.last_caption is None  # no replay of hidden result
        await engine.submit('three','third','third');await engine.wait_idle();assert hub.last_caption['segment_id']=='three'
        while not subscriber.queue.empty():events.append(subscriber.queue.get_nowait())
        assert [e['caption']['segment_id'] for e in events if e['type']=='caption']==['one','three']
        assert any(e.get('state')=='operator_hidden' for e in events)
        hub.set_state(hub.session_id,'stopped')
        hub.begin('next',direction={'id':'en-es','source_language':'en','target_language':'es'})
        assert hub.last_caption is None
        assert not hub.publish(results[-1])
        (out/'result.json').write_text(json.dumps({'status':'PASS','checks':8,'hidden_translation_preserved_in_results':True,'events':events},ensure_ascii=False,indent=2),encoding='utf-8')
    finally:await engine.close();hub.unsubscribe(subscriber)
    print('PASS: owner-only hold, clear, no hidden replay, stale rejection, session isolation')


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();asyncio.run(check(a.out))
