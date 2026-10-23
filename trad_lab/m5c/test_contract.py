"""No network: provider errors/tail/hide/DeepL schema contracts."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import unittest
from app.translation.engine import TranslationConfig,TranslationEngine,TranslationStatus
from app.translation.providers import DeepLTranslatorProvider
from app.translation.models import TranslationRequest
from app.overlay.hub import CaptionHub
from app.overlay.config import CaptionConfig
from trad_lab.m5c.runtime import SimulationProvider


class Contracts(unittest.IsolatedAsyncioTestCase):
    async def engine(self,provider,config=None):
        self.results=[];self.hub=CaptionHub(CaptionConfig());self.hub.begin('test',direction={'id':'en-es','source_language':'en','target_language':'es'})
        self.hub.set_state('test','live')
        async def result(r,s):self.results.append(r);self.hub.publish(r)
        engine=TranslationEngine(config or TranslationConfig(enabled=True,provider='mock',source_language='en',target_language='es'),provider,'test',result)
        await engine.start();self.addAsyncCleanup(engine.close);return engine

    async def test_delay_order_and_language(self):
        p=SimulationProvider(.002);e=await self.engine(p)
        for i in range(3):await e.submit(str(i),'140 over 19','140 over 19')
        await e.wait_idle();self.assertEqual([r.sequence for r in self.results],[1,2,3]);self.assertTrue(all(r.success for r in self.results));self.assertEqual(self.hub.sequence,3)
        self.assertEqual([r.target_language for r in p.requests],['es']*3)

    async def test_provider_error_complete_is_not_claimed(self):
        p=SimulationProvider(fail_ids={'bad'})
        e=await self.engine(p,TranslationConfig(enabled=True,provider='mock',source_language='en',target_language='es',retries=0))
        await e.submit('bad','aldosterone','aldosterone');await e.submit('good','90','90');await e.wait_idle()
        self.assertFalse(self.results[0].success)
        # Zero retries is a test fixture: avoid timing-dependent retry cooldown.
        # Runtime policy and its dedicated cooldown regressions remain unchanged.
        self.assertTrue(self.results[1].success);self.assertEqual(e.metrics.failures,1)
        e.rearm();await e.submit('after-rearm','90','90');await e.wait_idle()
        self.assertTrue(self.results[-1].success);self.assertEqual(self.hub.last_caption['segment_id'],'after-rearm')

    async def test_provider_timeout_is_finite(self):
        cfg=TranslationConfig(enabled=True,provider='mock',source_language='en',target_language='es',timeout_seconds=.01,retries=0)
        e=await self.engine(SimulationProvider(.1),cfg);await e.submit('slow','untreated','untreated');await e.wait_idle()
        self.assertFalse(self.results[0].success);self.assertEqual(e.metrics.timeouts,1);self.assertIsNone(self.hub.last_caption)

    async def test_no_tail_submission_or_cross_session_caption(self):
        e=await self.engine(SimulationProvider());await e.submit('ready','confirmed','confirmed');await e.wait_idle()
        previous=self.hub.sequence;self.assertFalse(self.hub.publish(replace(self.results[0],session_id='foreign',sequence=2)));self.assertEqual(self.hub.sequence,previous)
        self.assertNotIn('are associated with stepwise.',self.hub.last_caption['text'])

    async def test_close_pending_explicit_cancellation(self):
        e=await self.engine(SimulationProvider(.1));await e.submit('pending','dose','dose');await e.close()
        self.assertEqual(e.metrics.cancelled,1);self.assertEqual(self.results,[])

    async def test_deepl_wire_en_es_without_http(self):
        seen=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):return json.dumps({'translations':[{'text':'SIMULACIÓN de respuesta'}]}).encode()
        def opener(request,timeout):seen.append(json.loads(request.data));return Response()
        provider=DeepLTranslatorProvider('test-key-not-real',opener=opener)
        request=TranslationRequest('s','r',1,'140 over 19','140 over 19',(),'en','es',0.)
        self.assertEqual(await provider.translate(request),'SIMULACIÓN de respuesta')
        self.assertEqual(seen,[{'text':['140 over 19'],'source_lang':'EN','target_lang':'ES'}])


if __name__=='__main__':unittest.main()
