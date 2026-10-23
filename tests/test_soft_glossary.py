import asyncio
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from app.terminology.rollout import GlossaryConfig,MedicalRelease,RolloutController,session_normalizer,load_release
from app.captions.identity_normalizer import IdentityNormalizer
from app.captions.terminology_normalizer import TerminologyNormalizer
from app.main import Settings,create_app
from app.translation import TranslationConfig,TranslationEngine
from app.translation.providers import DeepLTranslatorProvider
from tests.test_operator_control import authorize,headers,local_client,controlled_relay

ROOT=Path(__file__).resolve().parents[1]


class SoftGlossaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.package=load_release(GlossaryConfig.release_path)

    def normalizer(self,mode='soft',lang='en'):
        legacy=IdentityNormalizer() if lang=='en' else TerminologyNormalizer.from_config()
        return session_normalizer(GlossaryConfig(mode=mode,state_path=''),lang,legacy)

    def test_all_657_pairs_available_in_both_languages(self):
        self.assertEqual(657,len(self.package.concepts))
        for c in self.package.concepts:
            for lang in ['en','es']:
                self.assertTrue(any(h['concept']['id']==c['id'] for h in self.package.matches(c[lang],lang)),(c['id'],lang))

    def test_only_evaluated_80_have_fuzzy_and_others_stay_exact(self):
        self.assertEqual(97,len(self.package.evaluated))
        self.assertEqual(80,sum(t is not None for t in self.package.thresholds.values()))
        self.assertEqual(560,sum(not c['asr_evaluated'] for c in self.package.concepts))
        self.assertTrue(all(c['fuzzy_threshold_en'] is None for c in self.package.concepts if not c['asr_evaluated']))

    def test_by_negation_quantity_and_pressure_controls(self):
        n=self.normalizer()
        self.assertEqual('No primary aldosteronism by this test; ≥5 mg.',n.normalize('a','No primary allosteronism by this test; ≥5 mg.').normalized_text)
        for text in ['primary hypotension','orthostatic hypertension','secondary hypotension','primary hypetension',
                     'physical inactivity','hyperkalemic metabolic alkalosis','diastolic blood pressures','cardiovascular risks',
                     'pharmacologic therapy','aldosterone-producing adenoma','tag_non-elvated blood pressure']:
            with self.subTest(text=text):self.assertEqual(text,n.normalize(text,text).normalized_text)

    def test_shadow_and_off_restore_legacy_outputs_and_no_translation_hints(self):
        text='primary allosteronism by this test'
        for mode in ['shadow','off']:
            n=self.normalizer(mode)
            self.assertEqual(text,n.normalize('a',text).normalized_text)
            self.assertFalse(getattr(n,'translation_context',lambda *args:'')('hypertension','en','es'))
        self.assertTrue(self.normalizer('shadow').normalize('a',text).suggestions)

    def test_span_recognition_does_not_expand_ambiguous_acronyms(self):
        n=self.normalizer()
        self.assertEqual('MRA and HR are undefined.',n.normalize('a','MRA and HR are undefined.').normalized_text)
        self.assertEqual('',self.package.translation_context('MRA and HR','en','es'))
        self.assertIn('hipertensión',self.package.translation_context('hypertension','en','es'))
        self.assertIn('hypertension',self.package.translation_context('hipertensión arterial','es','en'))

    def test_spanish_legacy_normalization_unchanged_with_expanded_catalog(self):
        text='Presión arterial systólica y diastólica.'
        original=TerminologyNormalizer.from_config().normalize('a',text)
        actual=self.normalizer(lang='es').normalize('a',text)
        self.assertEqual(original.normalized_text,actual.normalized_text)
        self.assertTrue(actual.glossary['translation_context_enabled'])

    def test_rollback_is_persisted_and_survives_missing_release(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ'):
            os.environ.pop('TRAD_GLOSSARY_MODE',None)
            config=GlossaryConfig(state_path=str(Path(folder)/'state.json'))
            controller=RolloutController(config)
            self.assertEqual('soft',controller.status()['effective_mode'])
            controller.change('off',0)
            restarted=RolloutController(replace(config,release_path=str(Path(folder)/'missing')))
            self.assertEqual('off',restarted.status()['effective_mode'])
            self.assertEqual(1,restarted.generation)
            with self.assertRaises(RuntimeError):controller.change('soft',0)

    def test_package_corruption_falls_back_and_does_not_break_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);(path/'manifest.json').write_text('{}')
            n=session_normalizer(GlossaryConfig(release_path=folder,state_path=''),'en',IdentityNormalizer())
            self.assertIsInstance(n,IdentityNormalizer)
            with self.assertRaises(ValueError):MedicalRelease(folder)

    def test_operator_change_requires_auth_idle_owner_and_current_revision(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ'):
            os.environ.pop('TRAD_GLOSSARY_MODE',None)
            settings=Settings(log_dir=folder,translation=TranslationConfig(),glossary=GlossaryConfig(state_path=str(Path(folder)/'state.json')))
            app=create_app(settings)
            with patch('app.main.relay',controlled_relay),local_client(app) as client:
                token=authorize(client);other=authorize(client)
                self.assertEqual(403,client.post('/api/operator/glossary',json={'mode':'off','generation':0}).status_code)
                self.assertEqual(200,client.post('/api/operator/glossary',headers=headers(token),json={'mode':'off','generation':0}).status_code)
                self.assertEqual(409,client.post('/api/operator/glossary',headers=headers(token),json={'mode':'soft','generation':0}).status_code)
                self.assertEqual(400,client.post('/api/operator/glossary',headers=headers(token),json={'mode':[],'generation':1}).status_code)
                with client.websocket_connect('ws://localhost/ws/session?direction=en-es',subprotocols=['operator.v1',token],headers={'origin':'http://localhost'}) as ws:
                    ws.receive_json();ws.receive_json()
                    self.assertEqual(409,client.post('/api/operator/glossary',headers=headers(token),json={'mode':'soft','generation':1}).status_code)
                    self.assertEqual(403,client.post('/api/operator/glossary',headers=headers(other),json={'mode':'soft','generation':1}).status_code)
                    ws.send_bytes(b'');ws.receive_json()
                self.assertEqual(200,client.post('/api/operator/glossary',headers=headers(token),json={'mode':'soft','generation':1}).status_code)
                self.assertEqual('soft',client.get('/api/operator/status',headers=headers(token)).json()['glossary']['effective_mode'])

    def test_research_and_original_bytes_remain_identical(self):
        baseline=json.loads((ROOT/'benchmarks/glossary_soft_v1/baseline.json').read_text(encoding='utf-8'))
        for r in baseline['protected_files']:
            self.assertEqual(r['sha256'],hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest(),r['path'])


class TerminologyTranslationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_pipeline_and_overlay_follow_soft_then_off_between_sessions(self):
        from websockets.asyncio.server import serve
        from urllib.parse import parse_qs,urlsplit
        requests=[];bodies=[]
        raw='No primary allosteronism by this test; keep ≥5 mg.'
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return b'{"translations":[{"text":"Traduccion de prueba"}]}'
        def opener(request,timeout):
            bodies.append(json.loads(request.data));return Response()
        class RecordingProvider(DeepLTranslatorProvider):
            async def translate(self,request):
                requests.append(request);return await super().translate(request)
        def factory(config,sid,callback):
            return TranslationEngine(config,RecordingProvider('test',opener=opener),sid,callback)
        async def wlk(ws):
            lang=parse_qs(urlsplit(ws.request.path).query)['language'][0]
            await ws.send(json.dumps(dict(type='config',useAudioWorklet=True,mode='full',
                session_language=lang,session_language_isolation=1)))
            async for pcm in ws:
                if not pcm:
                    await ws.send('{"type":"ready_to_stop"}');return
                await ws.send(json.dumps(dict(lines=[dict(text=raw,speaker=1)],buffer_transcription='')))
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ'):
            os.environ.pop('TRAD_GLOSSARY_MODE',None)
            async with serve(wlk,'127.0.0.1',0) as upstream:
                settings=Settings(log_dir=folder,wlk_url=f'ws://127.0.0.1:{upstream.sockets[0].getsockname()[1]}/asr',
                    glossary=GlossaryConfig(state_path=str(Path(folder)/'state.json')),
                    translation=TranslationConfig(enabled=True,provider='deepl',context_segments=0))
                app=create_app(settings)
                def operate():
                    with local_client(app) as client:
                        owner=authorize(client)
                        for generation,mode in enumerate(['soft','off']):
                            response=client.post('/api/operator/glossary',headers=headers(owner),json=dict(mode=mode,generation=generation))
                            self.assertEqual(200,response.status_code)
                            with client.websocket_connect('ws://localhost/ws/session?direction=en-es',
                                subprotocols=['operator.v1',owner],headers={'origin':'http://localhost'}) as ws:
                                ws.receive_json();config=ws.receive_json()
                                self.assertEqual(mode,config['glossary']['mode'])
                                ws.send_bytes(b'\0\0')
                                messages=[]
                                while True:
                                    msg=ws.receive_json();messages.append(msg)
                                    if msg['type']=='translation':break
                                    self.assertNotEqual('error',msg['type'],msg)
                                expected=raw.replace('allosteronism','aldosteronism') if mode=='soft' else raw
                                translated=next(m['translation'] for m in messages if m['type']=='translation')
                                self.assertEqual(raw,translated['raw_text'])
                                self.assertEqual(expected,translated['normalized_text'])
                                with client.websocket_connect('ws://localhost/ws/overlay') as overlay:
                                    snapshot=overlay.receive_json()
                                    self.assertEqual('Traduccion de prueba',snapshot['captions'][-1]['text'])
                                ws.send_bytes(b'')
                                while ws.receive_json().get('state')!='stopped':pass
                            deadline=time.monotonic()+2
                            while not client.get('/api/operator/status',headers=headers(owner)).json()['can_start']:
                                self.assertLess(time.monotonic(),deadline);time.sleep(.01)
                with patch('app.asr.whisperlivekit_client.build_translation_engine',factory):
                    await asyncio.wait_for(asyncio.to_thread(operate),20)
        self.assertEqual(2,len(requests))
        self.assertIn('primary aldosteronism',bodies[0]['context'])
        self.assertNotIn('context',bodies[1])

    async def test_optional_hint_failure_and_empty_segment_preserve_translation_contract(self):
        from tests.test_translation_engine import EchoProvider
        provider=EchoProvider()
        engine=TranslationEngine(TranslationConfig(enabled=True,provider='mock'),provider,'fallback')
        def fail(*args):raise ValueError('injected hint failure')
        engine.terminology_context=fail
        await engine.start()
        try:
            request=await engine.submit('a','hypertension','hypertension')
            empty=await engine.submit('b','',None)
            await engine.wait_idle()
            self.assertEqual('',request.terminology_context)
            self.assertEqual('',empty.terminology_context)
            self.assertEqual(['hypertension'],[r.normalized_text for r in provider.requests])
        finally:await engine.close()

    async def test_real_provider_body_adds_only_matched_pairs_and_rollback_removes_them(self):
        bodies=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return b'{"translations":[{"text":"ok"}]}'
        def opener(request,timeout):bodies.append(json.loads(request.data));return Response()
        provider=DeepLTranslatorProvider('test',opener=opener)
        config=TranslationConfig(enabled=True,provider='deepl',source_language='en',target_language='es',context_segments=0)
        for mode in ['soft','off']:
            n=SoftGlossaryTests().normalizer(mode)
            engine=TranslationEngine(config,provider,mode)
            engine.terminology_context=getattr(n,'translation_context',None)
            await engine.start()
            request=await engine.submit('one','hypertension','hypertension')
            await engine.wait_idle();await engine.close()
            self.assertEqual(request.normalized_text,'hypertension')
        self.assertEqual(['hypertension'],bodies[0]['text'])
        self.assertIn('hipertensión',bodies[0]['context'])
        self.assertNotIn('context',bodies[1])


if __name__=='__main__':unittest.main(verbosity=2)
