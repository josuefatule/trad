import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from trad_lab.m4c.incremental import Word
from .memory import MemorySocket,MemoryClosed
from .transport import Broker,TurboService,Limits,Outbox,TransportError

KEY='synthetic-lab-key-not-a-credential-123456789'


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='C:/live-captions/logs/trad_lab')
        self.root=Path(self.temp.name).resolve()
        assert self.root.is_relative_to(Path('C:/live-captions/logs/trad_lab').resolve())
        self.brokers=[]

    async def asyncTearDown(self):
        for b in self.brokers:b.close()
        self.temp.cleanup()

    def service(self,decode=None,limits=Limits()):
        broker=Broker(decode or (lambda a,s:[Word(' 140',0,.3),Word(' over',.3,.5),Word(' 19.',.5,.7)]),self.root/str(len(self.brokers)),limits)
        self.brokers.append(broker);return TurboService(broker,KEY)

    async def socket(self,service,sid='one',key=KEY,query=b'mode=full&language=en',client='127.0.0.1'):
        return await MemorySocket(service,'/asr',query=query,headers=[(b'x-m5b-service-key',key.encode()),(b'x-m5b-session-id',sid.encode())],client=client).open()

    async def collect(self,socket):
        messages=[]
        try:
            while True:messages.append(json.loads(await socket.recv()))
        except MemoryClosed:pass
        await socket.close();return messages

    async def test_auth_language_duplicates_remote_and_no_secret_evidence(self):
        service=self.service()
        for kwargs in ({'key':'wrong'},{'query':b'mode=full&language=es'},{'query':b'mode=full&language=en&language=en'},{'client':'192.0.2.1'}):
            with self.assertRaises(MemoryClosed):await self.socket(service,**kwargs)
        self.assertFalse(service.broker.active);self.assertFalse(service.broker.used_ids)

    async def test_pcm_large_frames_canonical_order_eof_and_tail(self):
        service=self.service();socket=await self.socket(service)
        collecting=asyncio.create_task(self.collect(socket))
        pcm=b'\0'*128000
        await socket.send(pcm);await socket.send(b'')
        messages=await collecting
        self.assertEqual(messages[-1]['type'],'ready_to_stop')
        self.assertEqual(messages[-1]['received_bytes'],len(pcm))
        self.assertEqual(messages[-1]['pcm_sha256'],hashlib.sha256(pcm).hexdigest())
        self.assertEqual(messages[-2]['lines'][0]['text'],' 140 over 19.')
        summary=json.loads(next(service.broker.root.glob('*/summary.json')).read_text())
        self.assertTrue(summary['transport_complete']);self.assertFalse(service.broker.poisoned)
        self.assertEqual(summary['frames'],2)
        self.assertNotIn(KEY,''.join(p.read_text() for p in service.broker.root.rglob('*.json*')))

    async def test_eof_no_extra_vote_and_unconfirmed_tail(self):
        service=self.service();socket=await self.socket(service);collecting=asyncio.create_task(self.collect(socket))
        await socket.send(b'\0'*64000);await socket.send(b'');messages=await collecting
        self.assertFalse(messages[-2]['lines']);self.assertTrue(messages[-1]['unconfirmed_eof_tail'])
        summary=json.loads(next(service.broker.root.glob('*/summary.json')).read_text())
        self.assertEqual(summary['transcription_completion'],'unconfirmed_tail')

    async def test_busy_and_sequential_sessions_do_not_share_words(self):
        service=self.service();first=await self.socket(service)
        self.assertEqual(json.loads(await first.recv())['session_id'],'one')
        with self.assertRaises(MemoryClosed):await self.socket(service,sid='two')
        collect=asyncio.create_task(self.collect(first));await first.send(b'');await collect
        second=await self.socket(service,sid='two');collect=asyncio.create_task(self.collect(second))
        await second.send(b'\0'*64000);await second.send(b'');messages=await collect
        self.assertTrue(all(p['session_id']=='two' for p in messages));self.assertFalse(messages[-2]['lines'])
        with self.assertRaises(MemoryClosed):await self.socket(service,sid='one')

    async def test_odd_pcm_and_audio_budget_fail_without_terminal(self):
        for pcm,limits in [(b'1',Limits()),(b'0'*8,replace(Limits(),audio_bytes=4))]:
            service=self.service(limits=limits);socket=await self.socket(service);collect=asyncio.create_task(self.collect(socket))
            await socket.send(pcm);messages=await collect
            self.assertTrue(any(p.get('type')=='error' for p in messages))
            self.assertFalse(any(p.get('type')=='ready_to_stop' for p in messages))

    async def test_decoder_timeout_quarantines_native_worker_no_retry(self):
        release=threading.Event()
        def blocked(a,s):release.wait(2);return []
        service=self.service(blocked,replace(Limits(),decode_seconds=.03,send_seconds=.1))
        socket=await self.socket(service);collect=asyncio.create_task(self.collect(socket))
        await socket.send(b'0'*64000);messages=await collect
        self.assertTrue(service.broker.poisoned)
        with self.assertRaises(MemoryClosed):await self.socket(service,sid='new')
        release.set();await asyncio.to_thread(service.broker.job.result,1)
        await asyncio.wrap_future(service.broker.executor.submit(lambda:None))
        self.assertFalse(any(m.get('type')=='ready_to_stop' for m in messages))

    async def test_oom_quarantines_and_idle_timeout_is_explicit(self):
        def oom(a,s):raise RuntimeError('CUDA out of memory')
        service=self.service(oom);socket=await self.socket(service);collect=asyncio.create_task(self.collect(socket))
        await socket.send(b'0'*64000);messages=await collect;self.assertTrue(service.broker.poisoned)
        idle=self.service(limits=replace(Limits(),idle_seconds=.02));socket=await self.socket(idle)
        messages=await self.collect(socket)
        self.assertTrue(any(m.get('type')=='error' for m in messages))
        self.assertFalse(idle.broker.poisoned)

    async def test_bounded_backpressure_and_message_budget(self):
        out=Outbox(replace(Limits(),queue_items=1,queue_bytes=100,json_message_bytes=100))
        await out.put({'a':'x'*20})
        blocked=asyncio.create_task(out.put({'b':'y'*20}))
        await asyncio.sleep(.01);self.assertFalse(blocked.done())
        await out.get();await blocked
        self.assertEqual(out.peak_items,1);self.assertLessEqual(out.peak_bytes,100)
        with self.assertRaises(TransportError):await out.put({'c':'z'*101})

    async def test_disconnect_without_eof_never_reports_complete(self):
        service=self.service();socket=await self.socket(service)
        await socket.recv();await socket.close()
        summary=json.loads(next(service.broker.root.glob('*/summary.json')).read_text())
        self.assertFalse(summary['transport_complete'])
        self.assertEqual(summary['transcription_completion'],'incomplete')

    async def test_failed_sender_and_blocked_close_have_bounded_cleanup(self):
        service=self.service(limits=replace(Limits(),send_seconds=.02,idle_seconds=.1))
        incoming=asyncio.Queue();await incoming.put({'type':'websocket.connect'})
        scope={'type':'websocket','path':'/asr','client':('127.0.0.1',1),
               'query_string':b'mode=full&language=en',
               'headers':[(b'x-m5b-service-key',KEY.encode()),(b'x-m5b-session-id',b'failed-send')]}
        async def send(message):
            if message['type']!='websocket.accept':await asyncio.sleep(2)
        await asyncio.wait_for(service(scope,incoming.get,send),.5)
        summary=json.loads(next(service.broker.root.glob('*/summary.json')).read_text())
        self.assertFalse(summary['transport_complete'])

    async def test_decode_is_serial_off_event_loop_while_heartbeat_progresses(self):
        import time
        identifiers=[];beats=[]
        main_thread=threading.get_ident()
        def decode(audio,start):
            identifiers.append(threading.get_ident());time.sleep(.025);return []
        service=self.service(decode);socket=await self.socket(service)
        collecting=asyncio.create_task(self.collect(socket))
        async def heartbeat():
            for _ in range(10):beats.append(True);await asyncio.sleep(.005)
        ticking=asyncio.create_task(heartbeat())
        await socket.send(b'\0'*128000);await socket.send(b'');await collecting;await ticking
        self.assertEqual(len(identifiers),2);self.assertEqual(len(set(identifiers)),1)
        self.assertNotEqual(identifiers[0],main_thread);self.assertEqual(len(beats),10)


if __name__=='__main__':unittest.main()
