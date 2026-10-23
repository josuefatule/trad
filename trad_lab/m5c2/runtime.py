"""Physical A only, DeepL OFF, private post-capture evidence with owner auth."""
import asyncio
import json
import os
from pathlib import Path
import re
import time
from contextlib import asynccontextmanager
from app.translation.engine import TranslationStatus
from trad_lab.m4b.tap import EvidenceWriter


def configure_environment():
    from trad_lab.m5b.runtime import configure_environment as base
    base()  # Drops inherited translation/key families; never reads .env.


def provider_from_config(config):
    if config.enabled or config.deepl_auth_key or config.provider:
        raise RuntimeError('C2-A requires translation completely disabled')
    return None,TranslationStatus('disabled',None,'Ensayo A: sin traducción ni captions')


def install(app):
    from trad_lab.m5c.runtime import install as base
    base(app)
    import app.translation.engine as engine
    engine.provider_from_config=provider_from_config
    from fastapi import HTTPException,Request
    from app.operator_control import local_request
    app.router.routes[:]=[r for r in app.router.routes if getattr(r,'path',None)!='/m5c/capabilities']
    writers={};sessions_closed=set()
    root=Path(os.environ['CAPTIONS_LOG_DIR']).resolve().parent/'browser_evidence'
    app.state.c2_evidence_writers=writers
    authority=app.state.operator_authority;hub=app.state.caption_hub
    original_lifespan=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(instance):
        async with original_lifespan(instance):
            try:yield
            finally:
                for state in writers.values():await asyncio.to_thread(state['writer'].close)
    app.router.lifespan_context=lifespan

    @app.get('/m5c/capabilities')
    async def capabilities():
        return {'phase':'M5-C2-A','physical_enabled':True,'real_deepl_enabled':False,
                'translation_enabled':False,'direction':'en-es','resampler':'fir127-candidate',
                'credit':'pcm_credit_v1','evidence':'owner_upload_v1'}

    @app.post('/api/m5c2/evidence')
    async def evidence(request:Request):
        received=time.perf_counter_ns();token=request.headers.get('x-operator-token')
        def allowed():return local_request(request,require_origin=True) and authority.valid(token) and authority.owner==token
        if not allowed():raise HTTPException(403,'Current owner required')
        body=bytearray()
        async for chunk in request.stream():
            if len(body)+len(chunk)>262144:raise HTTPException(413,'Evidence packet budget')
            body.extend(chunk)
        if not allowed():raise HTTPException(403,'Owner changed')
        try:
            data=json.loads(body);sid=data['session_id'];sequence=data['sequence'];rows=data['rows']
            if (not isinstance(sid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',sid) or sid!=hub.session_id or
                type(sequence) is not int or not isinstance(rows,list) or len(rows)>64 or type(data.get('final')) is not bool):raise ValueError()
            if sid in sessions_closed:raise ValueError('Already sealed')
            kinds={'pre','sent','track','worker','stop','eof','ack','asr','terminal','failure','clock','dom','control','context'}
            if any(not isinstance(r,dict) or r.get('kind') not in kinds for r in rows):raise ValueError('Invalid evidence row')
            # Reject identifiers/credentials entirely rather than echoing any request.
            for row in rows:
                if any(k in row for k in ('token','headers','url','deviceId','authorization')):raise ValueError('Forbidden evidence key')
            if sid not in writers:
                if sequence!=0:raise ValueError('Missing first packet')
                writers[sid]={'writer':EvidenceWriter(root/sid),'next':0,'busy':False}
            state=writers[sid];writer=state['writer']
            if state['busy'] or sequence!=state['next'] or writer.failed:raise ValueError('Sequence or writer failure')
            state['busy']=True
            try:
                if not writer.submit(rows,ack=sequence):raise RuntimeError('Writer budget/error')
                deadline=time.monotonic()+5
                while writer.acks.empty():
                    if writer.failed or time.monotonic()>=deadline:raise RuntimeError('Evidence write ACK failed')
                    await asyncio.sleep(.005)
                if writer.acks.get_nowait()!=sequence:raise RuntimeError('Writer ACK order')
                state['next']+=1
                if data['final']:
                    await asyncio.to_thread(writer.close)
                    if writer.failed:raise RuntimeError('Writer closure failed')
                    record={'session_id':sid,'packets':state['next'],'evidence_complete':True,
                            'capture_failed':bool(data.get('capture_failed')),'server_closed_ns':time.perf_counter_ns(),
                            'scope':'Evidence upload complete is not ASR/audio validity'}
                    (writer.path/'completion.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
                    sessions_closed.add(sid)
                return {'sequence':sequence,'written':True,'final':data['final'],
                        'server_received_ns':received,'server_written_ns':time.perf_counter_ns()}
            finally:state['busy']=False
        except HTTPException:raise
        except (ValueError,KeyError,TypeError,json.JSONDecodeError):raise HTTPException(409,'Invalid evidence sequence or schema')
        except Exception:raise HTTPException(503,'Evidence writer failed; retain CAPTURE, no retry')

