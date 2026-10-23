"""Bounded asynchronous evidence writer and transparent ASGI wire observer.

Never writes scope, headers, URLs/query strings, cookies or outbound auth.
Logging failure invalidates evidence; it never silently changes audio forwarding.
"""
import base64
import hashlib
import json
from pathlib import Path
import queue
import threading
import time

MAX_PACKET = 262144
MAX_TOTAL = 160 * 1024 * 1024
FORBIDDEN = ('token', 'secret', 'nonce', 'authorization', 'cookie', 'api_key', 'auth_key')


def safe(value):
    if isinstance(value, dict):
        return {k: safe(v) for k, v in value.items() if not any(x in k.lower() for x in FORBIDDEN)}
    if isinstance(value, list): return [safe(v) for v in value]
    return value


def projection(message):
    # A deliberate allowlist; no arbitrary websocket status/error string logging.
    return safe({k: message[k] for k in (
        'type', 'state', 'session_id', 'protocol_version', 'direction', 'capabilities',
        'wlk', 'payload', 'transcript', 'segmentation', 'normalization',
        'outcome', 'completion', 'translation_metrics', 'lab_decoder_evidence', 'session_language', 'session_language_isolation',
        'mode', 'useAudioWorklet', 'lines', 'buffer_transcription', 'buffer_diarization',
        'status', 'translation_status', 'reliability', 'normalization_mode', 'sample_rate') if k in message})


class EvidenceWriter:
    def __init__(self, path):
        self.path = Path(path); self.path.mkdir(parents=True, exist_ok=False)
        self.queue = queue.Queue(maxsize=32); self.failed = None; self.total = 0
        self.acks = queue.Queue(); self.closed = False
        self.thread = threading.Thread(target=self._run, daemon=True); self.thread.start()

    def submit(self, rows, ack=None):
        if self.closed: raise RuntimeError('Writer closed')
        # Only newly constructed, allowlisted evidence enters here.
        encoded = json.dumps(rows, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if self.failed: return False
        if len(encoded) > MAX_PACKET or self.total + len(encoded) > MAX_TOTAL:
            self.failed = 'evidence_size_limit'; return False
        self.total += len(encoded)
        try: self.queue.put_nowait((encoded, ack)); return True
        except queue.Full: self.failed = 'evidence_queue_overflow'; return False

    def _run(self):
        streams = {}; counts = {}; hashes = {}
        try:
            with (self.path/'events.jsonl').open('x', encoding='utf-8') as events:
                while True:
                    item = self.queue.get()
                    if item is None: break
                    encoded, ack = item
                    for row in json.loads(encoded):
                        row = safe(row)
                        binary = row.pop('b64', None)
                        if binary is not None:
                            kind = row['kind']
                            if kind not in {'pre', 'sent', 'received'}: raise ValueError('Unexpected binary kind')
                            payload = base64.b64decode(binary, validate=True)
                            width = 4 if kind == 'pre' else 2
                            if len(payload) % width: raise ValueError('Misaligned PCM')
                            if kind not in streams:
                                streams[kind] = (self.path/(kind+('.f32le' if width==4 else '.s16le'))).open('xb')
                                hashes[kind] = hashlib.sha256(); counts[kind] = 0
                            streams[kind].write(payload); hashes[kind].update(payload)
                            row['offset'] = counts[kind]; row['bytes'] = len(payload)
                            row['sha256'] = hashlib.sha256(payload).hexdigest(); counts[kind] += len(payload)
                        events.write(json.dumps(row, ensure_ascii=False)+'\n')
                    events.flush()
                    if ack is not None: self.acks.put(ack)
        except Exception as exc:
            self.failed = 'writer_'+type(exc).__name__
        finally:
            for f in streams.values(): f.close()
            (self.path/'writer.json').write_text(json.dumps({'failed': self.failed, 'input_json_bytes': self.total,
                'streams': {k: {'bytes': counts[k], 'sha256': h.hexdigest()} for k,h in hashes.items()}}, indent=2),encoding='utf-8')

    def close(self):
        if not self.closed:
            self.closed = True
            # Disk thread is independent of the audio/event callback.
            while self.thread.is_alive():
                try: self.queue.put(None, timeout=.1); break
                except queue.Full: pass
            self.thread.join(timeout=15)
            if self.thread.is_alive(): self.failed = 'writer_drain_timeout'


class WireTap:
    def __init__(self, app, root, path):
        self.app, self.root, self.path = app, Path(root), path
        self.serial = 0

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'websocket' or scope.get('path') != self.path:
            return await self.app(scope, receive, send)
        self.serial += 1
        writer = EvidenceWriter(self.root/f'wire_{self.serial:02d}')
        accepted = False; seq = 0
        async def observed_receive():
            nonlocal seq
            message = await receive()
            if accepted and message['type'] == 'websocket.receive' and message.get('bytes') is not None:
                audio = message['bytes']
                writer.submit([{'kind': 'received', 'seq': seq, 'py_ns': time.perf_counter_ns(),
                    'b64': base64.b64encode(audio).decode()}]); seq += 1
            return message
        async def observed_send(message):
            nonlocal accepted
            if message['type'] == 'websocket.accept': accepted = True
            if message['type'] == 'websocket.send' and message.get('text'):
                try:
                    payload = json.loads(message['text'])
                    if isinstance(payload, dict): writer.submit([{'kind': 'server_frame',
                        'py_ns': time.perf_counter_ns(), 'message': projection(payload)}])
                except ValueError: pass
            # Auth, accept/reject, bytes and all other messages remain exact.
            await send(message)
        try: await self.app(scope, observed_receive, observed_send)
        finally:
            import asyncio
            await asyncio.to_thread(writer.close)
