"""Controlled faults in memory only. No model, microphone or TCP server."""
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from trad_lab.m4c.incremental import Word
from .flow import CreditConnection, FlowTrace, PhaseError, phase_wait
from .memory import MemorySocket, MemoryClosed
from .runtime import DiagnosticBrowser, Diagnostics, FLOW, TRACE
from .transport import Broker, TurboService, Limits

KEY = 'memory-credit-test-key-not-a-live-secret-123456789'


class FlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='C:/live-captions/logs/trad_lab')
        self.root = Path(self.temp.name)
        self.brokers = []

    async def asyncTearDown(self):
        for broker in self.brokers:
            broker.close()
        self.temp.cleanup()

    def service(self, decode=None, limits=None):
        limits = limits or replace(Limits(), decode_seconds=.5, send_seconds=.2, idle_seconds=1.)
        decode = decode or (lambda a, s: [Word(' 140', 0, .2), Word(' over', .2, .4), Word(' 19.', .4, .6)])
        broker = Broker(decode, self.root / str(len(self.brokers)), limits)
        self.brokers.append(broker)
        return TurboService(broker, KEY)

    async def open(self, service, sid='flow', app=None):
        socket = await MemorySocket(app or service, '/asr', query=b'mode=full&language=en', headers=[
            (b'x-m5b-service-key', KEY.encode()), (b'x-m5b-session-id', sid.encode()),
            (b'x-m5b-pcm-credit', b'1')]).open()
        trace = FlowTrace(sid, self.root / f'{sid}.jsonl')
        connection = CreditConnection(socket, sid, trace, service.broker.limits)
        config = json.loads(await connection.recv())
        self.assertEqual(config['capabilities']['pcm_credit'], 1)
        return connection

    async def consume(self, connection, delay=0):
        messages = []
        while True:
            payload = json.loads(await connection.recv())
            if delay:
                await asyncio.sleep(delay)
            connection.delivered(payload)
            messages.append(payload)
            if payload.get('type') in ('ready_to_stop', 'error'):
                return messages

    async def test_phase_timeout_names_original_wait_and_cancels_task(self):
        ended = asyncio.Event()
        async def blocked():
            try:
                await asyncio.Future()
            finally:
                ended.set()
        trace = FlowTrace('typed', self.root / 'typed.jsonl')
        with self.assertRaises(PhaseError) as caught:
            await phase_wait('upstream_send', blocked(), .01, trace)
        self.assertEqual(caught.exception.transport_code, 'upstream_send_timeout')
        self.assertNotIsInstance(caught.exception, TimeoutError)
        self.assertTrue(ended.is_set())
        self.assertEqual(trace.state['failure_stage'], 'upstream_send_timeout')

    async def test_legacy_bounded_queue_can_exhaust_socket_send_while_decoder_works(self):
        queue = asyncio.Queue(maxsize=4)
        for _ in range(4):
            await queue.put(b'0' * 64000)
        # Four prefetched frames do not imply admission to the decoder.
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(queue.put(b'1' * 64000), .01)
        self.assertEqual(queue.qsize(), 4)
        self.assertEqual(sum(len(block) for block in list(queue._queue)), 256000)

    async def test_slow_decoder_and_consumer_succeed_without_raising_send_deadline(self):
        def decode(audio, start):
            time.sleep(.04)  # Longer than this test's socket-send deadline.
            return [Word(' aldosterone.', 0, .5)]
        service = self.service(decode)
        connection = await self.open(service)
        consuming = asyncio.create_task(self.consume(connection, .025))
        pcm = b'0' * 64000
        for _ in range(6):
            await connection.wait_audio_credit()
            await phase_wait('upstream_send', connection.send(pcm), .015, connection.trace)
            self.assertIsNotNone(connection.pending)
        await connection.wait_audio_credit()
        await phase_wait('upstream_send', connection.send(b''), .015, connection.trace)
        messages = await consuming
        await connection.close()
        self.assertEqual(messages[-1]['type'], 'ready_to_stop')
        self.assertEqual(connection.trace.state['acked_frames'], 6)
        self.assertEqual(connection.trace.state['acked_bytes'], 384000)
        self.assertEqual(connection.trace.state['pending_confirmed_words'], 0)
        summary = json.loads(next(service.broker.root.glob('*/summary.json')).read_text())
        self.assertTrue(summary['transport_complete'])
        self.assertFalse(service.broker.poisoned)

    async def test_credit_rejects_duplicate_out_of_order_hash_and_wrong_session(self):
        for change in ({'sha256': 'bad'}, {'frame_sequence': 1}, {'session_id': 'foreign'}):
            pcm = b'00'
            ack = {'type': 'pcm_ack', 'session_id': 'one', 'frame_sequence': 0,
                   'bytes': 2, 'received_bytes': 2, 'sha256': hashlib.sha256(pcm).hexdigest(), **change}
            messages = asyncio.Queue()
            messages.put_nowait(json.dumps({'backend': 'turbo-experimental', 'capabilities': {'pcm_credit': 1}}))
            messages.put_nowait(json.dumps(ack))
            fake = SimpleNamespace(send=AsyncMock(), recv=messages.get)
            connection = CreditConnection(fake, 'one', FlowTrace('one'))
            await connection.recv()
            await connection.send(pcm)
            with self.assertRaisesRegex(PhaseError, 'pcm_credit_integrity_error'):
                await connection.recv()
            self.assertIsNotNone(connection.pending)
            self.assertEqual(connection.trace.state['acked_bytes'], 0)

    async def test_no_second_frame_or_eof_accepted_without_credit(self):
        connection = CreditConnection(SimpleNamespace(send=AsyncMock()), 'one', FlowTrace('one'))
        connection.negotiated = True
        await connection.send(b'00')
        for data in (b'11', b''):
            with self.assertRaises(PhaseError):
                await connection.send(data)
        connection.credit_seconds = .01
        with self.assertRaisesRegex(PhaseError, 'pcm_credit_wait_timeout'):
            await connection.wait_audio_credit()
        self.assertFalse(connection.trace.state['eof_sent'])

    async def test_missing_credit_negotiation_blocks_before_pcm(self):
        fake = SimpleNamespace(send=AsyncMock(), recv=AsyncMock(return_value=json.dumps({'backend':'turbo-experimental'})))
        connection = CreditConnection(fake, 'one', FlowTrace('one'))
        with self.assertRaisesRegex(PhaseError, 'handshake_pcm_credit_missing'):
            await connection.recv()
        with self.assertRaises(PhaseError):
            await connection.send(b'00')
        fake.send.assert_not_called()

    async def test_backend_error_before_config_retains_original_phase(self):
        fake = SimpleNamespace(recv=AsyncMock(return_value=json.dumps({
            'type':'error','error':'decoder_timeout_native_call_quarantined','completion':'incomplete'})))
        connection = CreditConnection(fake, 'one', FlowTrace('one'))
        with self.assertRaisesRegex(PhaseError, 'backend_decoder_timeout_native_call_quarantined'):
            await connection.recv()
        self.assertFalse(connection.negotiated)

    async def test_duplicate_credit_does_not_acknowledge_a_second_frame(self):
        queue = asyncio.Queue()
        queue.put_nowait(json.dumps({'backend':'turbo-experimental','capabilities':{'pcm_credit':1}}))
        ack = {'type':'pcm_ack','session_id':'one','frame_sequence':0,'bytes':2,'received_bytes':2,
               'sha256':hashlib.sha256(b'00').hexdigest()}
        queue.put_nowait(json.dumps(ack));queue.put_nowait(json.dumps(ack))
        connection = CreditConnection(SimpleNamespace(send=AsyncMock(),recv=queue.get), 'one', FlowTrace('one'))
        await connection.recv();await connection.send(b'00')
        with self.assertRaisesRegex(PhaseError, 'pcm_credit_integrity_error'):
            await connection.recv()
        self.assertEqual(connection.trace.state['acked_frames'], 1)

    async def test_trace_budget_stops_before_starting_new_io(self):
        trace = FlowTrace('budget', self.root/'budget.jsonl', budget=1)
        action = AsyncMock()
        with self.assertRaisesRegex(PhaseError, 'transport_trace_budget'):
            await phase_wait('upstream_send', action(), .1, trace)
        action.assert_not_awaited()
        self.assertEqual(trace.state['failure_stage'], 'transport_trace_budget')

    async def test_congested_snapshot_send_records_unsubmitted_confirmations(self):
        service = self.service(limits=replace(Limits(), send_seconds=.03, idle_seconds=.3))
        async def app(scope, receive, send):
            async def blocked_send(message):
                payload = json.loads(message.get('text', '{}'))
                if payload.get('lines'):
                    await asyncio.Future()
                await send(message)
            await service(scope, receive, blocked_send)
        connection = await self.open(service, app=app)
        consuming = asyncio.create_task(self.consume(connection))
        for _ in range(2):
            await connection.wait_audio_credit()
            await connection.send(b'0' * 64000)
        with self.assertRaisesRegex(PhaseError, 'backend_snapshot_send_timeout'):
            await consuming
        await connection.close()
        summary = json.loads(next(service.broker.root.glob('*/summary.json')).read_text())
        self.assertFalse(summary['transport_complete'])
        self.assertEqual(summary['pending_submission_confirmed_words'], 3)
        self.assertEqual(summary['failure_stage'], 'snapshot_send_timeout')
        raw = next(service.broker.root.glob('*/raw.jsonl')).read_text()
        self.assertIn('19.', raw)  # Preserved, never clinically corrected or discarded.

    async def test_backend_decoder_timeout_is_distinct_from_eof_drain(self):
        release = threading.Event()
        def blocked(audio, start):
            release.wait(2.)
            return []
        service = self.service(blocked, replace(Limits(), decode_seconds=.25, send_seconds=.1))
        connection = await self.open(service)
        try:
            await connection.send(b'0' * 64000)
            with self.assertRaisesRegex(PhaseError, 'backend_decoder_timeout_native_call_quarantined'):
                await connection.recv()
            self.assertTrue(service.broker.poisoned)
            self.assertFalse(connection.trace.state['eof_sent'])
        finally:
            release.set()
            await asyncio.to_thread(service.broker.job.result, 2.)
            await asyncio.wrap_future(service.broker.executor.submit(lambda: None))
            await connection.close()

    async def test_browser_failure_preserves_received_not_delivered_confirmations(self):
        trace = FlowTrace('one')
        flow = CreditConnection(SimpleNamespace(), 'one', trace)
        flow.trace.state.update(received_snapshot_sequence=2, received_confirmed_words=9, pending_confirmed_words=9)
        diagnostics = Diagnostics()
        diagnostics.begin('one')
        wrapper = DiagnosticBrowser(SimpleNamespace(send_json=AsyncMock(side_effect=TimeoutError)), diagnostics, 'one')
        token = FLOW.set(flow)
        trace_token = TRACE.set(trace)
        try:
            with self.assertRaisesRegex(PhaseError, 'browser_delivery_timeout'):
                await wrapper.send_json({'type': 'asr', 'payload': {'adapter_sequence': 2, 'lines': []}})
        finally:
            FLOW.reset(token)
            TRACE.reset(trace_token)
        self.assertEqual(trace.state['pending_confirmed_words'], 9)
        self.assertEqual(trace.state['delivered_confirmed_words'], 0)

    async def test_disconnect_during_native_call_quarantines_until_evidence_closes(self):
        entered, release = threading.Event(), threading.Event()
        calls = 0
        def decode(audio, start):
            nonlocal calls
            calls += 1
            if calls == 2:
                entered.set()
                release.wait(2.)
            return [Word(' spironolactone.', 0, .5)]
        service = self.service(decode)
        async def app(scope, receive, send):
            async def disconnected_send(message):
                payload = json.loads(message.get('text', '{}'))
                if 'lines' in payload:
                    while not entered.is_set():
                        await asyncio.sleep(.001)
                    raise ConnectionError('synthetic disconnect')
                await send(message)
            await service(scope, receive, disconnected_send)
        socket = await MemorySocket(app, '/asr', query=b'mode=full&language=en', headers=[
            (b'x-m5b-service-key', KEY.encode()), (b'x-m5b-session-id', b'disconnect')]).open()
        await socket.recv()
        await socket.send(b'0' * 64000)
        await socket.send(b'0' * 64000)
        try:
            for _ in range(200):
                if service.broker.poisoned:
                    break
                await asyncio.sleep(.002)
            self.assertTrue(entered.is_set())
            self.assertTrue(service.broker.poisoned)
        finally:
            release.set()
            await asyncio.to_thread(service.broker.job.result, 2.)
            await asyncio.wrap_future(service.broker.executor.submit(lambda: None))
            await socket.close()
        summary = json.loads(next(service.broker.root.glob('*/summary.json')).read_text())
        self.assertFalse(summary['transport_complete'])
        self.assertTrue(summary['decoder_quarantined'])

    async def test_eof_preserves_provisional_tail_without_new_vote(self):
        service = self.service()
        connection = await self.open(service)
        collecting = asyncio.create_task(self.consume(connection))
        await connection.send(b'0' * 64000)
        await connection.wait_audio_credit()
        await connection.send(b'')
        messages = await collecting
        await connection.close()
        self.assertFalse(messages[-2]['lines'])
        self.assertEqual(''.join(w['text'] for w in messages[-1]['unconfirmed_eof_tail']), ' 140 over 19.')
        self.assertTrue(connection.trace.state['terminal_received'])


if __name__ == '__main__':
    unittest.main()
