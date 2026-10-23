"""Session-scoped PCM adapter to TRAD's full snapshot ASR contract.

No sockets, model imports, translation, reference prompts or environment reads.
The decoder is injected; the lab runner alone selects the cached Turbo model.
"""
from copy import deepcopy
import hashlib
import re
import numpy as np
from trad_lab.m4c.incremental import Config, Incremental

PROFILE = Config(mode='adaptive')
STEP_BYTES = 64000  # exactly 2 s, independently of incoming message partitions


class TurboAdapter:
    def __init__(self, session_id, decode, emit, *, raw_sink=lambda e: None,
                 backend=None, language='en', sample_rate=16000, channels=1):
        if backend != 'turbo-experimental':
            raise ValueError('Explicit lab-only backend selection required')
        if not isinstance(session_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', session_id):
            raise ValueError('Invalid lab session ID')
        if (language, sample_rate, channels) != ('en', 16000, 1):
            raise ValueError('Only explicit English mono s16le 16000 Hz is supported')
        self.session_id, self.emit, self.raw_sink = session_id, emit, raw_sink
        self.state = 'new'
        self.sequence = self.message_sequence = self.received_bytes = 0
        self.lines, self.tail, self.pending = [], [], bytearray()
        self.pcm_sha = hashlib.sha256()
        self.engine = Incremental(decode, self._event, PROFILE)

    def _send(self, payload):
        self.emit(deepcopy({**payload, 'session_id': self.session_id,
                            'adapter_sequence': self.message_sequence}))
        self.message_sequence += 1

    def start(self):
        if self.state != 'new':
            raise RuntimeError('START requires a new session object')
        self.state = 'live'
        self._send({'type': 'config', 'useAudioWorklet': True, 'mode': 'full',
                    'sample_rate': 16000, 'session_language_isolation': 1,
                    'session_language': 'en', 'backend': 'turbo-experimental',
                    'capabilities': {'unconfirmed_eof_tail': 1, 'word_timestamps': 1}})

    def request_stop(self, session_id):
        self._check(session_id)
        # Flush PCM is still accepted during draining, until the one audio EOF.
        self.state = 'draining'

    def _check(self, session_id):
        if session_id != self.session_id:
            raise ValueError('Session isolation violation')
        if self.state not in ('live', 'draining'):
            raise RuntimeError('Session is not accepting PCM/control')

    def push(self, session_id, sequence, pcm):
        self._check(session_id)
        if type(sequence) is not int or sequence != self.sequence:
            exc = ValueError('PCM sequence mismatch')
            self._fail(exc)
            raise exc
        if not isinstance(pcm, bytes) or len(pcm) % 2 or len(pcm) > STEP_BYTES:
            exc = ValueError('Expected at most 64000 bytes of whole s16le samples')
            self._fail(exc)
            raise exc
        self.sequence += 1
        if not pcm:
            return self._finish()
        self.pcm_sha.update(pcm)
        self.received_bytes += len(pcm)
        self.pending.extend(pcm)
        try:
            while len(self.pending) >= STEP_BYTES:
                block = bytes(self.pending[:STEP_BYTES])
                del self.pending[:STEP_BYTES]
                self.engine.push(np.frombuffer(block, dtype='<i2').astype('float32') / 32768.)
        except Exception as exc:
            self._fail(exc)
            raise

    def _fail(self, exc):
        self.state = 'failed'
        self._send({'type': 'error', 'error': type(exc).__name__,
                    'completion': 'incomplete', 'received_bytes': self.received_bytes})

    def _snapshot(self, provisional):
        self._send({'status': 'active_transcription', 'lines': self.lines,
                    'buffer_transcription': ''.join(w['text'] for w in provisional),
                    'buffer_diarization': '', 'buffer_translation': '',
                    'remaining_time_transcription': 0.,
                    'remaining_time_transcription_processing': 0.,
                    'remaining_time_transcription_policy': 0., 'remaining_time_diarization': 0.})

    def _event(self, event):
        self.raw_sink(deepcopy(event))
        if event['type'] == 'update':
            words = event['confirmed']
            if words:
                text = ''.join(w['text'] for w in words)
                self.lines.append({'id': f'{self.session_id}:commit-{len(self.lines)+1}',
                                   'speaker': None, 'text': text,
                                   'start': words[0]['start'], 'end': words[-1]['end'],
                                   'words': deepcopy(words)})
                if len(self.lines) > 6000 or sum(len(x['text']) for x in self.lines) > 300000:
                    raise RuntimeError('Full snapshot history budget exceeded')
            self._snapshot(event['provisional'])
        elif event['type'] == 'eof':
            self.tail = deepcopy(event['unconfirmed_tail'])
            self._send({'type': 'ready_to_stop', 'unconfirmed_eof_tail': self.tail,
                        'audio_eof': True, 'received_bytes': self.received_bytes,
                        'pcm_sha256': self.pcm_sha.hexdigest(),
                        'tail_policy': 'Never promoted to lines, confirmed text or READY'})

    def _finish(self):
        try:
            if self.pending:
                block = bytes(self.pending)
                self.pending.clear()
                self.engine.push(np.frombuffer(block, dtype='<i2').astype('float32') / 32768.)
            stats = self.engine.finish()
            self.state = 'stopped'
            return stats
        except Exception as exc:
            self._fail(exc)
            raise
