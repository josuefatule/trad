"""Authenticated ASGI transport around the unchanged M5-A adapter.

One accepted session and one worker. Native decoder timeouts quarantine the
broker: cancellation is never advertised as termination of a CUDA call.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import secrets
import time
import threading
from urllib.parse import parse_qsl
from trad_lab.m5a.adapter import TurboAdapter, STEP_BYTES


class TransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class Limits:
    frame_bytes: int = 1048576
    audio_bytes: int = 230400000
    queue_items: int = 8
    queue_bytes: int = 8388608
    json_message_bytes: int = 2000000
    trace_bytes: int = 268435456
    decode_seconds: float = 30.
    send_seconds: float = 5.
    idle_seconds: float = 30.
    session_seconds: float = 7200.


class Outbox:
    def __init__(self, limits):
        self.limits=limits
        self.queue=asyncio.Queue()
        self.condition=asyncio.Condition()
        self.bytes=self.peak_bytes=self.peak_items=0

    async def put(self, message):
        encoded=json.dumps(message,ensure_ascii=False)
        size=len(encoded.encode('utf-8'))
        if size>min(self.limits.json_message_bytes,self.limits.queue_bytes):raise TransportError('asr_message_budget')
        async with self.condition:
            while self.queue.qsize()>=self.limits.queue_items or self.bytes+size>self.limits.queue_bytes:
                await self.condition.wait()
            self.queue.put_nowait((encoded,size))
            self.bytes+=size
            self.peak_bytes=max(self.peak_bytes,self.bytes)
            self.peak_items=max(self.peak_items,self.queue.qsize())

    async def get(self):
        encoded,size=await self.queue.get()
        async with self.condition:
            self.bytes-=size
            self.condition.notify_all()
        return encoded


class Trace:
    def __init__(self, root, limits):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=False)
        self.limits=limits;self.bytes=0;self.audio_bytes=0;self.frames=0
        self.digest=hashlib.sha256()
        self.lock=threading.RLock()
        self.produced_sequence=self.submitted_sequence=None
        self.produced_words=self.submitted_words=0
        self.failure_stage=None
        self.handles={name:(self.root/name).open('wb') for name in ('received.s16le','frames.jsonl','raw.jsonl','asr.jsonl','transport.jsonl')}

    def json(self, name, data):
        encoded=(json.dumps(data,ensure_ascii=False)+'\n').encode('utf-8')
        with self.lock:
            if self.bytes+len(encoded)>self.limits.trace_bytes:raise TransportError('trace_budget')
            self.handles[name].write(encoded);self.bytes+=len(encoded)

    def event(self,stage,event,**metadata):
        self.json('transport.jsonl',{'perf_counter_ns':time.perf_counter_ns(),'stage':stage,'event':event,**metadata})

    def fail(self,stage,kind):
        if self.failure_stage is None:self.failure_stage=stage+'_'+kind
        self.event(stage,kind)

    def pcm(self, data):
        if self.audio_bytes+len(data)>self.limits.audio_bytes:raise TransportError('pcm_budget')
        self.json('frames.jsonl',{'sequence':self.frames,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                                'offset':self.audio_bytes,'eof':not data,'perf_counter_ns':time.perf_counter_ns()})
        self.frames+=1;self.audio_bytes+=len(data);self.digest.update(data)
        self.handles['received.s16le'].write(data)

    def close(self, summary):
        for handle in self.handles.values():handle.close()
        (self.root/'summary.json').write_text(json.dumps({**summary,'frames':self.frames,'received_bytes':self.audio_bytes,
             'pcm_sha256':self.digest.hexdigest(),'json_bytes':self.bytes,
             'produced_snapshot_sequence':self.produced_sequence,'submitted_snapshot_sequence':self.submitted_sequence,
             'produced_confirmed_words':self.produced_words,'submitted_confirmed_words':self.submitted_words,
             'pending_submission_confirmed_words':self.produced_words-self.submitted_words,
             'failure_stage':self.failure_stage,
             'delivery_scope':'ASGI send returned is not consumer receipt; correlate with TRAD transport trace.'},indent=2),encoding='utf-8')


class Broker:
    def __init__(self, decoder, root, limits=Limits()):
        self.decoder=decoder;self.root=Path(root);self.limits=limits
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='m5b-decoder')
        self.active=False;self.poisoned=False;self.serial=0;self.used_ids=set();self.job=None

    def reserve(self, session_id):
        if self.poisoned:raise TransportError('decoder_quarantined')
        if self.active:raise TransportError('backend_busy')
        if session_id in self.used_ids or len(self.used_ids)>=6000:raise TransportError('session_identity_reused_or_budget')
        self.used_ids.add(session_id);self.active=True;self.serial+=1
        return self.root/f'session_{self.serial:04d}'

    async def call(self, function, *args):
        if self.poisoned:raise TransportError('decoder_quarantined')
        self.job=self.executor.submit(function,*args)
        wrapped=asyncio.wrap_future(self.job)
        wrapped.add_done_callback(lambda f:None if f.cancelled() else f.exception())
        try:
            return await asyncio.wait_for(asyncio.shield(wrapped),self.limits.decode_seconds)
        except TimeoutError:
            self.poisoned=True
            raise TransportError('decoder_timeout_native_call_quarantined')
        except asyncio.CancelledError:
            self.poisoned=True
            raise
        except Exception as exc:
            if 'out of memory' in str(exc).lower():self.poisoned=True
            raise

    def close(self):
        self.executor.shutdown(wait=False,cancel_futures=True)


class TurboService:
    def __init__(self, broker, service_key):
        if len(service_key)<32:raise ValueError('Independent local service key required')
        self.broker=broker;self.service_key=service_key

    def authorized(self, scope):
        try:local=ipaddress.ip_address(scope.get('client',('',))[0]).is_loopback
        except ValueError:local=False
        headers=dict(scope.get('headers',[]))
        supplied=headers.get(b'x-m5b-service-key',b'')
        return local and secrets.compare_digest(supplied,self.service_key.encode())

    async def __call__(self, scope, receive, send):
        if scope['type']=='lifespan':
            while True:
                event=await receive()
                if event['type']=='lifespan.startup':await send({'type':'lifespan.startup.complete'})
                elif event['type']=='lifespan.shutdown':
                    self.broker.close();await send({'type':'lifespan.shutdown.complete'});return
        if scope['type']=='http':
            status=200 if scope['path']=='/health' and self.authorized(scope) else 403
            body=json.dumps({'ready':status==200 and not self.broker.poisoned,'active':self.broker.active,
                             'backend':'turbo-experimental','language':'en'}).encode() if status==200 else b'{}'
            await send({'type':'http.response.start','status':status,'headers':[(b'content-type',b'application/json')]})
            await send({'type':'http.response.body','body':body});return
        if scope['type']!='websocket':return
        pairs=parse_qsl(scope.get('query_string',b'').decode('ascii',errors='replace'),keep_blank_values=True)
        headers=dict(scope.get('headers',[]))
        sid=headers.get(b'x-m5b-session-id',b'').decode('ascii',errors='replace')
        credit=headers.get(b'x-m5b-pcm-credit',b'')==b'1'
        valid=(scope['path']=='/asr' and sorted(pairs)==[('language','en'),('mode','full')]
               and re.fullmatch(r'[A-Za-z0-9_-]{1,80}',sid))
        if not self.authorized(scope) or not valid:
            await send({'type':'websocket.close','code':4403});return
        try:folder=self.broker.reserve(sid)
        except TransportError:
            await send({'type':'websocket.close','code':4413});return
        limits=self.broker.limits;loop=asyncio.get_running_loop();outbox=Outbox(limits)
        trace=None;terminal=False;tail=[];failure=None;sender=None;worker=None;started=time.monotonic()
        def emit(payload):
            if credit and payload.get('type')=='config':
                payload={**payload,'capabilities':{**payload.get('capabilities',{}),'pcm_credit':1,'pcm_frame_bytes':64000}}
            trace.json('asr.jsonl',payload)
            if 'lines' in payload:
                trace.produced_sequence=payload['adapter_sequence']
                trace.produced_words=sum(len(line['words']) for line in payload['lines'])
                trace.event('snapshot_produced','done',adapter_sequence=trace.produced_sequence,confirmed_words=trace.produced_words)
            future=asyncio.run_coroutine_threadsafe(outbox.put(payload),loop)
            try:future.result(timeout=limits.send_seconds)
            except BaseException:
                future.cancel();trace.fail('snapshot_enqueue','timeout');raise TransportError('outbound_backpressure_timeout')
        def start():
            nonlocal trace
            trace=Trace(folder,limits)
            adapter=TurboAdapter(sid,self.broker.decoder,emit,raw_sink=lambda e:trace.json('raw.jsonl',e),backend='turbo-experimental')
            adapter.start();return adapter
        def push(adapter, pcm):
            trace.pcm(pcm)
            if not pcm:return adapter.push(sid,adapter.sequence,b'')
            for offset in range(0,len(pcm),STEP_BYTES):
                adapter.push(sid,adapter.sequence,pcm[offset:offset+STEP_BYTES])
        async def send_frames():
            nonlocal terminal,tail
            from .flow import phase_wait
            while True:
                encoded=await outbox.get()
                await phase_wait('snapshot_send',send({'type':'websocket.send','text':encoded}),limits.send_seconds,trace)
                payload=json.loads(encoded)
                if 'lines' in payload:
                    trace.submitted_sequence=payload['adapter_sequence']
                    trace.submitted_words=sum(len(line['words']) for line in payload['lines'])
                    trace.event('snapshot_submitted','done',adapter_sequence=trace.submitted_sequence,confirmed_words=trace.submitted_words)
                if payload.get('type')=='ready_to_stop':
                    tail=payload['unconfirmed_eof_tail'];terminal=True;return
                if payload.get('type')=='error':raise TransportError('adapter_error')
        async def accept_audio(adapter):
            from .flow import phase_wait
            while True:
                remaining=limits.session_seconds-(time.monotonic()-started)
                if remaining<=0:raise TransportError('session_time_budget')
                message=await phase_wait('backend_receive',receive(),min(limits.idle_seconds,remaining),trace)
                if message['type']=='websocket.disconnect':raise TransportError('client_disconnected_before_eof')
                pcm=message.get('bytes')
                if not isinstance(pcm,bytes) or len(pcm)%2 or len(pcm)>min(limits.frame_bytes,64000 if credit else limits.frame_bytes):raise TransportError('invalid_pcm_frame')
                trace.event('pcm_admission','received',frame_sequence=trace.frames,bytes=len(pcm))
                trace.event('decoder','begin',frame_sequence=trace.frames,deadline_seconds=limits.decode_seconds)
                try:await self.broker.call(push,adapter,pcm)
                except BaseException as exc:
                    trace.event('decoder','interrupted',native_still_running=bool(self.broker.job and not self.broker.job.done()))
                    if isinstance(exc,TransportError):trace.fail('decoder','timeout' if 'timeout' in str(exc) else 'error')
                    raise
                trace.event('decoder','done',frame_sequence=trace.frames-1)
                if credit and pcm:
                    ack={'type':'pcm_ack','session_id':sid,'frame_sequence':trace.frames-1,
                         'bytes':len(pcm),'received_bytes':trace.audio_bytes,'sha256':hashlib.sha256(pcm).hexdigest()}
                    await phase_wait('pcm_credit_enqueue',outbox.put(ack),limits.send_seconds,trace)
                if not pcm:return
        try:
            await receive()  # ASGI websocket.connect; never saved with headers.
            await send({'type':'websocket.accept'})
            sender=asyncio.create_task(send_frames())
            adapter=await self.broker.call(start)
            worker=asyncio.create_task(accept_audio(adapter))
            done,_=await asyncio.wait({sender,worker},return_when=asyncio.FIRST_COMPLETED)
            for task in done:task.result()
            if worker in done:
                await asyncio.wait_for(sender,limits.send_seconds)
            elif terminal:
                await worker
            if not terminal:raise TransportError('missing_terminal')
        except BaseException as exc:
            failure=getattr(exc,'transport_code',None) or (type(exc).__name__ if not isinstance(exc,TransportError) else str(exc))
            try:await asyncio.wait_for(send({'type':'websocket.send','text':json.dumps({'type':'error','error':failure,'completion':'incomplete'})}),limits.send_seconds)
            except BaseException:pass
        finally:
            for task in (worker,sender):
                if task and not task.done():task.cancel()
            await asyncio.gather(*(t for t in (worker,sender) if t),return_exceptions=True)
            # A live native call retains ownership of its Trace until it exits.
            def summary():
                return {'transport_complete':terminal and not failure,'transcription_completion':'incomplete' if failure else 'unconfirmed_tail' if tail else 'all_emitted_words_confirmed',
                        'unconfirmed_eof_tail':tail,'failure':failure,'decoder_quarantined':self.broker.poisoned,
                        'outbox_peak_bytes':outbox.peak_bytes,'outbox_peak_items':outbox.peak_items,'pcm_credit_protocol':int(credit)}
            job=self.broker.job
            if trace:
                if job and not job.done():
                    self.broker.poisoned=True
                    job.add_done_callback(lambda f:trace.close(summary()))
                else:trace.close(summary())
            self.broker.active=False
            try:await asyncio.wait_for(send({'type':'websocket.close','code':1000 if terminal and not failure else 1011}),limits.send_seconds)
            except BaseException:pass
