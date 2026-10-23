"""Actual repaired ASGI route with active session/owner rotation; no TCP/provider/mic."""
import asyncio
import base64
import json
import os
from pathlib import Path
from unittest.mock import patch
from trad_lab.m5b.memory import MemoryHTTP


async def check(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    os.environ['CAPTIONS_LOG_DIR']=str(out/'operational_logs')
    from trad_lab.m5c2b import runtime
    with patch.object(runtime,'read_local_config',lambda:{'key':'test-provider-key-not-real','url':'https://api-free.deepl.com/v2/translate'}):
        from app.main import app
    authority=app.state.operator_authority;hub=app.state.caption_hub
    owner=authority.issue();other=authority.issue();authority.owner=owner
    hub.begin('stream-evidence',direction={'id':'en-es','source_language':'en','target_language':'es'});hub.set_state(hub.session_id,'live')
    headers=lambda token:{'x-operator-token':token,'origin':'http://127.0.0.1:18010','host':'127.0.0.1:18010'}
    pcm=b'\x17\0'*2048;pre=b'\0'*8192
    packet={'session_id':hub.session_id,'sequence':0,'final':False,'capture_failed':False,
            'rows':[{'kind':'pre','sequence':0,'samples':2048,'channels':1,'sample_rate':48000,'b64':base64.b64encode(pre).decode()}]}
    checks=0
    try:
        async with MemoryHTTP(app) as http:
            config=(await http.get('/api/overlay/config')).json();assert config['mode']=='timed_queue';checks+=1
            assert (await http.post('/api/m5c2/evidence',headers=headers(other),json=packet)).status_code==403;checks+=1
            r=await http.post('/api/m5c2/evidence',headers=headers(owner),json=packet)
            assert r.status_code==200 and r.json()['written'] and not r.json()['final'] and r.json()['writer_json_bytes']>0
            assert hub.state=='live';checks+=2
            first_bytes=r.json()['writer_json_bytes']
            assert (await http.post('/api/m5c2/evidence',headers=headers(owner),json=packet)).status_code==409;checks+=1
            new_owner=authority.resume(owner,authority.resume_secrets[owner])
            final={**packet,'sequence':1,'final':True,'rows':[{'kind':'sent','sequence':0,'eof':False,'b64':base64.b64encode(pcm).decode()}, {'kind':'sent','sequence':1,'eof':True,'b64':''}]}
            assert (await http.post('/api/m5c2/evidence',headers=headers(owner),json=final)).status_code==403;checks+=1
            # Like the browser auth getter, the next packet uses the recovered current owner.
            hub.set_state(hub.session_id,'stopped')
            r=await http.post('/api/m5c2/evidence',headers=headers(new_owner),json=final)
            assert r.status_code==200 and r.json()['final'] and r.json()['writer_json_bytes']>first_bytes;checks+=1
            assert (await http.post('/api/m5c2/evidence',headers=headers(new_owner),json=final)).status_code==409;checks+=1
            path=out/'browser_evidence/stream-evidence'
            assert (path/'pre.f32le').read_bytes()==pre and (path/'sent.s16le').read_bytes()==pcm
            assert json.loads((path/'completion.json').read_text())['capture_failed'] is False;checks+=2
            hub.begin('failure-evidence',direction={'id':'en-es','source_language':'en','target_language':'es'});hub.set_state(hub.session_id,'live')
            p={**packet,'session_id':hub.session_id}
            assert (await http.post('/api/m5c2/evidence',headers=headers(new_owner),json={**p,'rows':[{'kind':'clock','token':'forbidden-test'}]})).status_code==409;checks+=1
            assert (await http.post('/api/m5c2/evidence',headers=headers(new_owner),json=p)).status_code==200
            writer=app.state.c2_evidence_writers[hub.session_id]['writer']
            with patch.object(writer,'submit',return_value=False):
                assert (await http.post('/api/m5c2/evidence',headers=headers(new_owner),json={**p,'sequence':1})).status_code==503;checks+=1
            record={'status':'PASS','checks':checks,'scope':'Active ASGI evidence packets, write ACKs, real disk, recovered owner, seal, duplicate/foreign token/forbidden schema/disk failure; no model/API/microphone/TCP'}
            (out/'result.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
    finally:
        for state in app.state.c2_evidence_writers.values():state['writer'].close()


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();asyncio.run(check(a.out))
