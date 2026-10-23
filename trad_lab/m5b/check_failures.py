"""Real copied TRAD routes with injected faults, entirely ASGI in memory."""
import argparse
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
from unittest.mock import patch

from .memory import MemoryHTTP, MemorySocket, MemoryClosed, connector
from .transport import Broker, TurboService, Limits
from trad_lab.m4c.incremental import Word

ROOT = Path(__file__).resolve().parents[2]


async def check(out):
    if ROOT.name != 'copy' or not ROOT.is_relative_to(Path('C:/live-captions/logs/trad_lab')):
        raise ValueError('Fresh experimental copy required')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    key = 'in-memory-failure-key-not-a-secret-123456789012345'
    keyfile = out / 'test-key.txt'
    keyfile.write_text(key, encoding='utf-8')
    os.environ.update(M5B_BACKEND='turbo', M5B_SERVICE_KEY_FILE=str(keyfile), CAPTIONS_LOG_DIR=str(out / 'logs'))
    from app.main import create_app, Settings
    from . import runtime
    results = []
    for fault, expected in [('send', 'upstream_send_timeout'), ('browser', 'browser_delivery_timeout'),
                            ('eof', 'eof_drain_timeout')]:
        settings = Settings(stop_timeout=.04, log_dir=str(out / 'logs'),
                            reliability=replace(Settings().reliability, websocket_send_seconds=.03))
        app = create_app(settings)
        broker = Broker(lambda a, s: [Word(' 140', 0, .2), Word(' over', .2, .4), Word(' 19.', .4, .6)],
                        out / fault, replace(Limits(), idle_seconds=.3, send_seconds=.1))
        service = TurboService(broker, key)
        normal_connect = connector(service)
        class Wire:
            def __init__(self):
                self.queue = asyncio.Queue()
                self.queue.put_nowait(json.dumps({'type':'config','mode':'full','useAudioWorklet':True,
                    'backend':'turbo-experimental','session_language':'en','session_language_isolation':1,
                    'capabilities':{'pcm_credit':1}}))
            async def recv(self):return await self.queue.get()
            async def send(self, pcm):assert pcm == b''
            async def close(self):pass
        async def network(url, **kwargs):
            if fault == 'eof':return Wire()
            sock = await normal_connect(url, **kwargs)
            if fault == 'send':
                class Blocked:
                    def __getattr__(self, name):return getattr(sock, name)
                    async def send(self, data):await asyncio.Future()
                return Blocked()
            return sock
        async def fault_app(scope, receive, send):
            async def wrapped(message):
                payload = json.loads(message.get('text', '{}'))
                if fault == 'browser' and payload.get('type') == 'asr' and payload.get('payload', {}).get('lines'):
                    await asyncio.sleep(4.)  # Exercises the real copied 2 s send bound.
                await send(message)
            await app(scope, receive, wrapped)
        try:
          async with app.router.lifespan_context(app), MemoryHTTP(app) as client:
            owner = (await client.get('/api/operator/bootstrap')).json()['control_token']
            headers = {'x-operator-token':owner, 'origin':'http://127.0.0.1:18010'}
            with patch.object(runtime, 'network_connect', network):
                socket = await MemorySocket(fault_app, '/ws/session', port=18010, query=b'direction=en-es', headers=[
                    (b'host', b'127.0.0.1:18010'), (b'origin', b'http://127.0.0.1:18010'),
                    (b'sec-websocket-protocol', ('operator.v1, '+owner).encode())], subprotocols=['operator.v1',owner]).open()
                messages = []
                while True:
                    message = json.loads(await socket.recv())
                    messages.append(message)
                    if message.get('type') == 'config':break
                sid = message['session_id']
                if fault == 'eof':
                    response = await client.post('/api/operator/stop', headers=headers, json={'session_id':sid})
                    assert response.status_code == 200
                    await socket.send(b'')
                else:
                    await socket.send(b'0' * 64000)
                    if fault == 'browser':await socket.send(b'0' * 64000)
                try:
                    while True:messages.append(json.loads(await socket.recv()))
                except MemoryClosed:pass
                await socket.close()
                status = (await client.get('/api/operator/status', headers=headers)).json()
                reason = status['reliability']['reason']
                assert reason == expected, (fault, reason, expected)
                assert status['reliability']['outcome'] == 'incomplete' and not status['session_open']
                assert not status['reliability']['asr_final']
                assert bool(status['reliability']['stop_reason']) == (fault == 'eof')
                errors = [message for message in messages if message.get('type') == 'error']
                assert errors and errors[-1]['error_code'] == expected
                assert 'STOP' not in errors[-1]['message']
                diag = status['experimental_asr']
                assert diag['error_category'] == expected
                if fault == 'browser':assert diag['transport']['pending_confirmed_words'] == 3
                results.append({'fault':fault,'reason':reason,'status':'PASS','session_id':sid,
                                'reliability':status['reliability'], 'diagnostics':diag,
                                'error_message':errors[-1]['message']})
        finally:
            broker.close()
    (out / 'result.json').write_text(json.dumps({'status':'PASS','cases':results,
        'scope':'Copied app routes and unchanged ASR synthetic decoder through ASGI queues. Test-only short deadlines. No TCP, GPU or microphone.'},
        ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status':'PASS','cases':len(results)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    asyncio.run(check(parser.parse_args().out))
