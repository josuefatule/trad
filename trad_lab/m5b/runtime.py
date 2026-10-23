"""Hooks installed exclusively in the frozen experimental app copy."""
import contextvars
from copy import deepcopy
import json
import os
from pathlib import Path
import secrets
from urllib.parse import parse_qsl,urlsplit
from websockets.asyncio.client import connect as network_connect
from websockets.exceptions import InvalidHandshake

SESSION=contextvars.ContextVar('m5b_session',default=None)
FLOW=contextvars.ContextVar('m5b_flow',default=None)
TRACE=contextvars.ContextVar('m5b_trace',default=None)


async def relay_wait(stage, awaitable, seconds=None):
    from .flow import phase_wait
    return await phase_wait(stage, awaitable, seconds, TRACE.get())


def configure_environment():
    # Called by COPY/app/main.py instead of loading any .env file.
    log_dir=os.environ.get('CAPTIONS_LOG_DIR')
    for name in list(os.environ):
        if name.startswith(('DEEPL_','TRANSLATION_','SEGMENT_','NORMALIZER_','OPERATOR_','RELIABILITY_','CAPTION_','CAPTIONS_','WLK_')):os.environ.pop(name)
    os.environ.update(TRANSLATION_ENABLED='0',TRANSLATION_PROVIDER='',TRANSLATION_SOURCE_LANGUAGE='en',
                      TRANSLATION_TARGET_LANGUAGE='es',CAPTIONS_LANGUAGE='en',CAPTIONS_LOG_RAW='0',
                      WLK_WS_URL='ws://127.0.0.1:18000/asr')
    if log_dir:os.environ['CAPTIONS_LOG_DIR']=log_dir


async def connect(url,**kwargs):
    if os.environ.get('M5B_BACKEND') not in ('turbo','wlk'):raise RuntimeError('Explicit lab backend required')
    parts=urlsplit(url)
    if (parts.scheme,parts.hostname,parts.port,parts.path)!=('ws','127.0.0.1',18000,'/asr'):
        raise RuntimeError('Only isolated backend 18000 permitted')
    if sorted(parse_qsl(parts.query))!=[('language','en'),('mode','full')]:raise RuntimeError('English full mode required')
    if os.environ['M5B_BACKEND']=='turbo':
        session=SESSION.get()
        if not session:raise RuntimeError('Missing Operator session context')
        key=Path(os.environ['M5B_SERVICE_KEY_FILE']).read_text(encoding='utf-8').strip()
        kwargs['additional_headers']={'X-M5B-Service-Key':key,'X-M5B-Session-Id':session}
        kwargs['additional_headers']['X-M5B-PCM-Credit']='1'
        kwargs['max_queue']=4
    try:
        connection=await relay_wait('upstream_connect',network_connect(url,**kwargs),kwargs.get('open_timeout',10.))
    except InvalidHandshake:
        # The original operator classifier maps any textual HTTP 403 to DeepL.
        # Keep this backend rejection distinct, without exposing key/headers.
        raise RuntimeError('experimental_asr_handshake_rejected') from None
    if os.environ['M5B_BACKEND']=='turbo':
        from .flow import CreditConnection,FlowTrace
        connection=CreditConnection(connection,session,TRACE.get() or FlowTrace(session))
        FLOW.set(connection)
    return VerifiedConnection(connection,os.environ['M5B_BACKEND'])


class VerifiedConnection:
    def __init__(self,connection,backend):self.connection=connection;self.backend=backend;self.first=True
    def __getattr__(self,name):return getattr(self.connection,name)
    async def recv(self):
        raw=await self.connection.recv()
        if self.first:
            self.first=False;payload=json.loads(raw)
            if self.backend=='turbo' and payload.get('backend')!='turbo-experimental':raise ValueError('Experimental backend selection mismatch')
            if self.backend=='wlk' and payload.get('backend')=='turbo-experimental':raise ValueError('Rollback backend selection mismatch')
        return raw


class Diagnostics:
    def __init__(self):self.current=None;self.data={}

    def begin(self,session):
        self.current=session
        self.data={'session_id':session,'backend':os.environ.get('M5B_BACKEND','turbo'),
                   'transport_completion':'in_progress','transcription_completion':'in_progress',
                   'eof_observed':False,
                   'unconfirmed_eof_tail':[],
                   'known_errors':['140 over 90 → 140 over 19','aldosterone → eldest run','10-year ASCVD risk → tenure',
                                   'Late medical revisions, medication names and speaker corrections require review'],
                   'alert_scope':'Known candidate risks, not occurrence detection or automatic correction; agreement is not medical certainty'}

    def snapshot(self):return deepcopy(self.data)


class DiagnosticBrowser:
    def __init__(self,browser,diagnostics,session):
        self.browser=browser;self.diagnostics=diagnostics;self.session=session
        self.last_notified=-1

    def __getattr__(self,name):return getattr(self.browser,name)

    async def receive(self):
        flow=FLOW.get()
        if flow:
            await flow.wait_audio_credit()
            if flow.last_ack and flow.last_ack['frame_sequence']>self.last_notified:
                await self.send_json({'type':'pcm_ack',**flow.last_ack})
                self.last_notified=flow.last_ack['frame_sequence']
        return await relay_wait('capture_receive',self.browser.receive())

    async def send_json(self,message):
        if self.diagnostics.current!=self.session:raise RuntimeError('Stale diagnostic session')
        payload=message.get('payload',{})
        if message.get('type')=='config' and FLOW.get():
            message={**message,'experimental_transport':{
                'pcm_credit':1,'frame_bytes':64000,
                'credit_seconds':FLOW.get().credit_seconds+2.,
                'pacing':'realtime by default; accelerated requires explicit selection'}}
        if message.get('type')=='asr' and payload.get('type')=='ready_to_stop':
            tail=deepcopy(payload.get('unconfirmed_eof_tail',[]))
            self.diagnostics.data.update(unconfirmed_eof_tail=tail,
                eof_observed=True,
                transcription_completion=('not_reported_by_wlk' if 'unconfirmed_eof_tail' not in payload else
                                           'unconfirmed_tail' if tail else 'all_emitted_words_confirmed'))
        if message.get('type')=='status' and message.get('state')=='stopped':
            self.diagnostics.data['transport_completion']=message.get('completion','complete')
            message={**message,'experimental_asr':self.diagnostics.snapshot()}
        await relay_wait('browser_delivery',self.browser.send_json(message),2.)
        if FLOW.get() and message.get('type')=='asr':
            FLOW.get().delivered(payload)


async def experimental_relay(browser,settings,session_id,caption_hub=None):
    from app.asr.whisperlivekit_client import relay as original
    diagnostics=caption_hub._m5b_diagnostics
    diagnostics.begin(session_id)
    token=SESSION.set(session_id)
    flow_token=FLOW.set(None)
    from .flow import FlowTrace,PhaseError
    log_dir=os.environ.get('CAPTIONS_LOG_DIR')
    trace=FlowTrace(session_id,Path(log_dir)/'transport'/f'{session_id}.jsonl' if log_dir else None)
    trace_token=TRACE.set(trace)
    diagnostics.data['transport']=trace.state
    try:
        await original(DiagnosticBrowser(browser,diagnostics,session_id),settings,session_id,caption_hub)
    except BaseException as exc:
        # The original relay wraps upstream receive failures; retain their phase.
        cause=exc;seen=set();phase=None
        while cause and id(cause) not in seen:
            seen.add(id(cause))
            if isinstance(cause,PhaseError):phase=cause;break
            cause=cause.__cause__ or cause.__context__
        if isinstance(exc,TimeoutError) and phase is None:
            phase=PhaseError('unattributed_transport')
        diagnostics.data.update(transport_completion='incomplete',transcription_completion='incomplete',
          error_category=phase.transport_code if phase else 'experimental_asr_handshake_rejected' if str(exc)=='experimental_asr_handshake_rejected' else type(exc).__name__)
        if phase:
            trace.state['failure_stage']=phase.transport_code
            raise phase from exc
        raise
    finally:
        try:trace.event('session','finished',**trace.state)
        finally:TRACE.reset(trace_token);FLOW.reset(flow_token);SESSION.reset(token)


class DiagnosticMiddleware:
    def __init__(self,app,diagnostics):self.app=app;self.diagnostics=diagnostics

    async def __call__(self,scope,receive,send):
        if scope['type']=='websocket' and scope['path']=='/ws/session':
            directions=[v for k,v in parse_qsl(scope.get('query_string',b'').decode()) if k=='direction']
            if directions and directions!=['en-es']:
                await send({'type':'websocket.close','code':4400});return
        if scope['type']=='http' and scope['path']=='/api/operator/status':
            start=None;chunks=[]
            async def intercept(message):
                nonlocal start
                if message['type']=='http.response.start':start=message;return
                if message['type']=='http.response.body':
                    chunks.append(message.get('body',b''))
                    if message.get('more_body'):return
                    body=b''.join(chunks)
                    if start['status']==200:
                        payload=json.loads(body);payload['experimental_asr']=self.diagnostics.snapshot()
                        body=json.dumps(payload,ensure_ascii=False).encode('utf-8')
                    headers=[(k,v) for k,v in start['headers'] if k.lower()!=b'content-length']
                    await send({**start,'headers':headers+[(b'content-length',str(len(body)).encode())]})
                    await send({'type':'http.response.body','body':body})
            await self.app(scope,receive,intercept);return
        await self.app(scope,receive,send)


def install(app):
    from fastapi.responses import FileResponse
    import app.main as main
    diagnostics=Diagnostics()
    app.state.caption_hub._m5b_diagnostics=diagnostics
    app.state.m5b_diagnostics=diagnostics
    app.add_middleware(DiagnosticMiddleware,diagnostics=diagnostics)
    @app.get('/m5b/file-capture')
    async def file_capture():return FileResponse(main.ROOT/'templates/m5b_file_capture.html')
