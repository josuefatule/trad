"""Real relay with in-memory transport; no listening sockets or microphone."""
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from app.asr.whisperlivekit_client import relay, starting_connection
from app.captions.segment_manager import SegmentConfig
from app.reliability import ReliabilityConfig
from app.translation import TranslationConfig
from trad_lab.m4c.incremental import Word
from .adapter import TurboAdapter


class MemoryUpstream:
    def __init__(self):
        self.queue=asyncio.Queue()
        self.adapter=TurboAdapter('bridge',lambda a,s:[Word(' orthostatic',0,.4),Word(' hypotension.',.4,.8)],
                                  lambda p:self.queue.put_nowait(json.dumps(p)),backend='turbo-experimental')
        self.adapter.start()
        self.closed=False

    async def recv(self):return await self.queue.get()

    async def send(self,pcm):
        self.adapter.push('bridge',self.adapter.sequence,pcm)
        await asyncio.sleep(0)

    async def close(self):self.closed=True


class MemoryBrowser:
    def __init__(self, blocks=None):
        self.blocks=iter(blocks if blocks is not None else [b'\0'*64000,b'\0'*64000,b''])
        self.messages=[]

    async def receive(self):
        await asyncio.sleep(0)
        return {'type':'websocket.receive','bytes':next(self.blocks)}

    async def send_json(self,payload):self.messages.append(payload)


class RelayTests(unittest.IsolatedAsyncioTestCase):
    def settings(self):
        return SimpleNamespace(language='en',direction='en-es',require_language_ack=True,
            segments=SegmentConfig(),reliability=ReliabilityConfig(),log_raw=False,
            translation=TranslationConfig(enabled=False,source_language='en',target_language='es'),
            connect_timeout=.5,stop_timeout=2,wlk_url='ws://memory-only.invalid/asr')

    async def test_actual_relay_handshake_snapshot_segmentation_eof_disabled_translation(self):
        upstream=MemoryUpstream();browser=MemoryBrowser()
        with patch('app.asr.whisperlivekit_client.connect',AsyncMock(return_value=upstream)) as connect, \
             patch('app.translation.engine.DeepLTranslatorProvider',side_effect=AssertionError('DeepL forbidden')) as deepl:
            await asyncio.wait_for(relay(browser,self.settings(),'bridge'),4)
        self.assertEqual(connect.await_count,1);deepl.assert_not_called()
        self.assertTrue(upstream.closed)
        config=next(p for p in browser.messages if p.get('type')=='config')
        self.assertEqual(config['translation_status']['state'],'disabled')
        ready=[s for p in browser.messages for s in p.get('segmentation',{}).get('ready_segments',[])]
        self.assertEqual(' '.join(s['text'] for s in ready),'orthostatic hypotension.')
        final=browser.messages[-1]
        self.assertEqual((final['state'],final['completion']),('stopped','complete'))
        self.assertFalse(any(p.get('type')=='translation' for p in browser.messages))

    async def test_actual_handshake_rejects_unattested_language_before_pcm(self):
        upstream=SimpleNamespace(recv=AsyncMock(return_value=json.dumps({'type':'config','mode':'full','useAudioWorklet':True,
            'session_language_isolation':0,'session_language':'es'})),close=AsyncMock())
        with patch('app.asr.whisperlivekit_client.connect',AsyncMock(return_value=upstream)):
            with self.assertRaisesRegex(ValueError,'language isolation'):
                async with starting_connection('ws://memory-only.invalid',self.settings(),AsyncMock(),json.loads):
                    self.fail('Should reject before opening the session')
        upstream.close.assert_awaited_once()

    async def test_real_relay_forwards_tail_without_promoting_it(self):
        upstream=MemoryUpstream();browser=MemoryBrowser([b'\0'*64000,b''])
        with patch('app.asr.whisperlivekit_client.connect',AsyncMock(return_value=upstream)):
            await asyncio.wait_for(relay(browser,self.settings(),'bridge'),4)
        final=next(p for p in browser.messages if p.get('payload',{}).get('type')=='ready_to_stop')
        self.assertEqual(''.join(w['text'] for w in final['payload']['unconfirmed_eof_tail']),' orthostatic hypotension.')
        self.assertEqual(final['transcript']['confirmed_text'],'')
        self.assertEqual(final['segmentation']['ready_segments'],())
        # Existing relay completion describes transport/drain; it does not
        # certify that the EOF tail has been confirmed or shown in captions.
        self.assertEqual(browser.messages[-1]['completion'],'complete')


if __name__=='__main__':unittest.main()
