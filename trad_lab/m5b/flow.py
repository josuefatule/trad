"""Experimental transport credits and phase diagnostics. No ASR policy changes.

A credit is issued after a PCM frame has been decoded and its preceding ASR
snapshots have passed through the consumer. It is not an ASR confirmation vote.
"""
import asyncio
import hashlib
import inspect
import json
import re
from pathlib import Path
import time

from .transport import Limits
from fastapi import WebSocketDisconnect
from websockets.exceptions import ConnectionClosed


class PhaseError(RuntimeError):
    # A diagnosed failure must escape the original startup ConnectionError retry.
    def __init__(self, stage, kind='timeout'):
        self.stage = stage
        self.transport_code = f'{stage}_{kind}'
        super().__init__(self.transport_code)


class FlowTrace:
    """Bounded metadata-only trace, in the private lab log directory."""
    def __init__(self, session, path=None, budget=8388608):
        self.session, self.path, self.budget = session, Path(path) if path else None, budget
        self.bytes = self.sequence = 0
        self.state = {'sent_frames': 0, 'acked_frames': 0, 'sent_bytes': 0, 'acked_bytes': 0,
                      'received_snapshot_sequence': None, 'delivered_snapshot_sequence': None,
                      'received_confirmed_words': 0, 'delivered_confirmed_words': 0,
                      'pending_confirmed_words': 0, 'failure_stage': None,
                      'eof_sent': False, 'terminal_received': False}
        if self.path:
            allowed = Path('C:/live-captions/logs/trad_lab').resolve()
            if not self.path.resolve().is_relative_to(allowed):
                raise ValueError('Private laboratory trace path required')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('x', encoding='utf-8'):
                pass

    def event(self, stage, event, **metadata):
        # Call sites pass only controlled stage names, counters, offsets and hashes.
        row = {'session_id': self.session, 'sequence': self.sequence,
               'perf_counter_ns': time.perf_counter_ns(), 'stage': stage, 'event': event, **metadata}
        encoded = (json.dumps(row) + '\n').encode()
        if self.bytes + len(encoded) > self.budget:
            self.state['failure_stage'] = self.state['failure_stage'] or 'transport_trace_budget'
            raise PhaseError('transport_trace', 'budget')
        if self.path:
            with self.path.open('ab') as stream:
                stream.write(encoded)
        self.bytes += len(encoded)
        self.sequence += 1

    def fail(self, stage, kind):
        if self.state['failure_stage'] is None:
            self.state['failure_stage'] = f'{stage}_{kind}'
        self.event(stage, kind)


async def phase_wait(stage, awaitable, seconds=None, trace=None):
    """Own exactly one deadline; preserve the phase of nested failures."""
    try:
        if trace:
            trace.event(stage, 'begin', deadline_seconds=seconds)
    except BaseException:
        if inspect.iscoroutine(awaitable):awaitable.close()
        raise
    try:
        result = await asyncio.wait_for(awaitable, seconds) if seconds is not None else await awaitable
    except PhaseError:
        raise
    except TimeoutError as exc:
        if trace:
            trace.fail(stage, 'timeout')
        raise PhaseError(stage) from exc
    except asyncio.CancelledError:
        if trace:
            trace.event(stage, 'cancelled')
        raise
    except Exception as exc:
        disconnected = isinstance(exc, (WebSocketDisconnect, ConnectionClosed, ConnectionError))
        if trace:
            trace.fail(stage, 'disconnected' if disconnected else 'error')
        if disconnected:
            raise PhaseError(stage, 'disconnected') from exc
        raise
    if trace:
        trace.event(stage, 'done')
    return result


class CreditConnection:
    """One frame outstanding, validated cumulative bytes/sequence/SHA credit.

    recv() is owned by the original serial TRAD consumer. Consequently the credit
    following a snapshot is read only after TRAD processes/delivers that snapshot.
    Waiting for decoder progress happens outside the existing 3 s socket send.
    """
    def __init__(self, connection, session, trace, limits=Limits()):
        self.connection, self.session, self.trace, self.limits = connection, session, trace, limits
        self.ready = asyncio.Event()
        self.ready.set()
        self.pending = None
        self.last_ack = None
        self.error = None
        self.negotiated = False
        # Existing decoder + backend send + TRAD browser-delivery bounds.
        self.credit_seconds = limits.decode_seconds + limits.send_seconds + 2.
        self.first = True

    def __getattr__(self, name):
        return getattr(self.connection, name)

    async def wait_audio_credit(self):
        try:
            await phase_wait('pcm_credit_wait', self.ready.wait(), self.credit_seconds, self.trace)
            if self.error:
                raise self.error
        except BaseException as exc:
            self.error = exc
            raise

    async def send(self, pcm):
        if not self.negotiated:
            raise PhaseError('pcm_credit', 'not_negotiated')
        if self.error:
            raise self.error
        if self.pending is not None or not isinstance(pcm, bytes) or len(pcm) % 2 or len(pcm) > 64000:
            raise PhaseError('pcm_credit', 'invalid_frame_or_missing_credit')
        if pcm:
            state = self.trace.state
            self.pending = {'frame_sequence': state['sent_frames'], 'bytes': len(pcm),
                            'received_bytes': state['sent_bytes'] + len(pcm),
                            'sha256': hashlib.sha256(pcm).hexdigest()}
            state['sent_frames'] += 1
            state['sent_bytes'] += len(pcm)
            self.ready.clear()
        else:
            if self.trace.state['eof_sent']:
                raise PhaseError('audio_eof', 'duplicate')
            self.trace.state['eof_sent'] = True
        frame_metadata = dict(self.pending or {'bytes': 0})
        # The frozen relay applies the existing socket-send deadline at this call.
        await self.connection.send(pcm)
        self.trace.event('upstream_send', 'submitted', **frame_metadata)

    async def recv(self):
        try:
            while True:
                raw = await phase_wait('upstream_receive', self.connection.recv(), trace=self.trace)
                payload = json.loads(raw)
                if payload.get('type') == 'error':
                    code = payload.get('error', '')
                    kind = code if isinstance(code, str) and re.fullmatch('[a-z_]{1,100}', code) else 'transport_error'
                    self.trace.fail('backend', kind)
                    raise PhaseError('backend', kind)
                if self.first:
                    self.first = False
                    if payload.get('backend') != 'turbo-experimental':
                        raise PhaseError('handshake', 'backend_mismatch')
                    if payload.get('capabilities', {}).get('pcm_credit') != 1:
                        raise PhaseError('handshake', 'pcm_credit_missing')
                    self.negotiated = True
                if payload.get('type') == 'pcm_ack':
                    if payload.get('session_id') != self.session or self.pending is None or any(
                            payload.get(key) != value for key, value in self.pending.items()):
                        raise PhaseError('pcm_credit', 'integrity_error')
                    state = self.trace.state
                    state['acked_frames'] += 1
                    state['acked_bytes'] += self.pending['bytes']
                    self.trace.event('pcm_credit', 'accepted', **self.pending)
                    self.last_ack = dict(self.pending)
                    self.pending = None
                    self.ready.set()
                    continue
                if 'lines' in payload:
                    self.trace.state['received_snapshot_sequence'] = payload['adapter_sequence']
                    self.trace.state['received_confirmed_words'] = sum(len(line['words']) for line in payload['lines'])
                    self.trace.state['pending_confirmed_words'] = (self.trace.state['received_confirmed_words']
                                                                  - self.trace.state['delivered_confirmed_words'])
                if payload.get('type') == 'ready_to_stop':
                    if self.pending is not None or not self.trace.state['eof_sent']:
                        raise PhaseError('audio_eof', 'terminal_before_credit')
                    self.trace.state['terminal_received'] = True
                return raw
        except BaseException as exc:
            if not isinstance(exc, asyncio.CancelledError):
                self.error = exc
                self.ready.set()
            raise

    def delivered(self, payload):
        if 'lines' in payload:
            state = self.trace.state
            state['delivered_snapshot_sequence'] = payload['adapter_sequence']
            state['delivered_confirmed_words'] = sum(len(line['words']) for line in payload['lines'])
            state['pending_confirmed_words'] = state['received_confirmed_words'] - state['delivered_confirmed_words']
            self.trace.event('browser_delivery', 'snapshot_delivered',
                             adapter_sequence=payload['adapter_sequence'], confirmed_words=state['delivered_confirmed_words'])

    async def close(self):
        self.ready.set()
        prior_failure = self.trace.state['failure_stage']
        try:
            await phase_wait('upstream_close', self.connection.close(), 1., self.trace)
        except Exception:
            if not self.error and not prior_failure:
                raise
