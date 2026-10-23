"""Actual owner-authenticated evidence routes in memory, no TCP or microphone."""
import asyncio
import base64
import json
import os
from pathlib import Path
from trad_lab.m5b.memory import MemoryHTTP


async def check(out):
    out=Path(out);out.mkdir(exist_ok=False,parents=True)
    os.environ['CAPTIONS_LOG_DIR']=str(out/'operational_logs')
    from app.main import app
    authority=app.state.operator_authority;hub=app.state.caption_hub
    owner=authority.issue();outsider=authority.issue();authority.owner=owner
    hub.begin('evidence-test',direction={'id':'en-es','source_language':'en','target_language':'es'});hub.set_state(hub.session_id,'stopped')
    def headers(token=owner):return {'x-operator-token':token,'origin':'http://127.0.0.1:18010'}
    pre=b'\x00'*8192;sent=b'\x00\x00'*683
    rows=[{'kind':'pre','b64':base64.b64encode(pre).decode(),'sequence':0,'first_sample':0,'samples':2048,'channels':1,'sample_rate':48000},
          {'kind':'sent','b64':base64.b64encode(sent).decode(),'sequence':0,'eof':False},
          {'kind':'sent','b64':'','sequence':1,'eof':True}]
    try:
      async with MemoryHTTP(app) as http:
        caps=(await http.get('/m5c/capabilities')).json();assert caps['physical_enabled'] and not caps['real_deepl_enabled']
        body={'session_id':hub.session_id,'sequence':0,'rows':rows,'final':True,'capture_failed':False}
        assert (await http.post('/api/m5c2/evidence',headers=headers(outsider),json=body)).status_code==403
        assert (await http.post('/api/m5c2/evidence',headers=headers(),json={**body,'sequence':1})).status_code==409
        response=await http.post('/api/m5c2/evidence',headers=headers(),json=body)
        assert response.status_code==200 and response.json()['written']
        assert (await http.post('/api/m5c2/evidence',headers=headers(),json=body)).status_code==409
        path=out/'browser_evidence'/hub.session_id
        assert (path/'pre.f32le').read_bytes()==pre and (path/'sent.s16le').read_bytes()==sent
        assert json.loads((path/'completion.json').read_text())['evidence_complete']
        (out/'result.json').write_text(json.dumps({'status':'PASS','checks':7,'real_deepl_enabled':False,'evidence_bytes_exact':True}),encoding='utf-8')
    finally:
      for state in app.state.c2_evidence_writers.values():state['writer'].close()
    print('PASS: C2-A disabled translator, owner-only evidence, order, bytes and closure')


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();asyncio.run(check(a.out))
