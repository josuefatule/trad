from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app.captions.identity_normalizer import IdentityNormalizer
from app.captions.terminology_normalizer import TerminologyNormalizer
from app.terminology.rollout import GlossaryConfig,RolloutController,load_release,session_normalizer
from app.terminology.correction_patch import CorrectionPatch,load_patch,audit_catalog,lexical_key
from app.translation import TranslationConfig,TranslationEngine
from app.translation.providers import DeepLTranslatorProvider

ROOT=Path(__file__).resolve().parents[1]


class CorrectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release=load_release(GlossaryConfig.release_path)
        cls.patch=load_patch(GlossaryConfig.patch_path,cls.release)

    def normalizer(self,mode='soft',enabled=True,language='en',**kwargs):
        legacy=IdentityNormalizer() if language=='en' else TerminologyNormalizer.from_config()
        config=GlossaryConfig(mode=mode,patch_enabled=enabled,state_path='',**kwargs)
        return session_normalizer(config,language,legacy)

    def test_observed_phrase_is_repaired_with_negation_by_and_numbers_intact(self):
        source='There is no evidence of primary adosterizm by this test; keep 5 mg, not 50 mg.'
        r=self.normalizer().normalize('one',source)
        self.assertEqual(source,r.raw_text)
        self.assertEqual(source.replace('adosterizm','aldosteronism'),r.normalized_text)
        self.assertEqual(1,len(r.corrections))
        c=r.corrections[0]
        self.assertEqual(c.source,source[c.start:c.end])
        self.assertEqual('medical_observed_spelling',c.rule)
        again=self.normalizer().normalize('two',r.normalized_text)
        self.assertEqual(r.normalized_text,again.normalized_text)
        self.assertFalse(again.corrections)

    def test_case_and_multiple_occurrences_have_nonoverlapping_raw_offsets(self):
        source='PRIMARY ADOSTERIZM; Primary adosterizm; primary adosterizm.'
        r=self.normalizer().normalize('t',source)
        self.assertEqual('PRIMARY ALDOSTERONISM; Primary aldosteronism; primary aldosteronism.',r.normalized_text)
        self.assertEqual(3,len(r.corrections))
        for a,b in zip(r.corrections,r.corrections[1:]):self.assertLessEqual(a.end,b.start)
        for c in r.corrections:self.assertEqual(c.source,source[c.start:c.end])

    def test_unattested_or_ambiguous_words_identifiers_and_quantities_are_preserved(self):
        cases=['adosterizm','primary outlawed','primary adosterism','secondary adosterizm',
            'primary adosterizms','tag_primary adosterizm','tag_x primary adosterizm',
            'non-primary adosterizm','primary adosterizm_like',"primary adosterizm's",'primary, adosterizm',
            'primary 5 adosterizm','hypotension','hypetension','systolic blood pressure',
            'diastolic blood pressure','a systolic blood pressure','the astolic blood pressure',
            'high rate','physical inactivity','physical in activity','5 mg, not 15 mg','Not 50.mg.']
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(text,self.normalizer().normalize('t',text).normalized_text)

    def test_resisted_is_review_only_and_pressure_space_join_remains_independent(self):
        for source,expected in [('The patient has resisted hypertension.','The patient has resisted hypertension.'),
            ('The patient has resisted hyper tension.','The patient has resisted hypertension.')]:
            r=self.normalizer().normalize('t',source)
            self.assertEqual(expected,r.normalized_text)
            suggestions=[s for s in r.suggestions if s.rule=='medical_context_review_only']
            self.assertEqual(1,len(suggestions))
            self.assertEqual('resistant hypertension',suggestions[0].candidate)
            self.assertEqual(0,suggestions[0].confidence)
            self.assertEqual(source[suggestions[0].start:suggestions[0].end],suggestions[0].source)
            self.assertNotIn('resistant hypertension',self.normalizer().translation_context(r.normalized_text,'en','es'))

    def test_off_shadow_and_patch_only_switch_restore_expected_layers(self):
        source='No primary adosterizm and hyper tension by this test.'
        for mode in ['off','shadow']:
            r=self.normalizer(mode).normalize('t',source)
            self.assertEqual(source,r.normalized_text)
        shadow=self.normalizer('shadow').normalize('t',source)
        self.assertTrue(any(s.candidate=='primary aldosteronism' for s in shadow.suggestions))
        disabled=self.normalizer(enabled=False)
        self.assertEqual('No primary adosterizm and hypertension by this test.',disabled.normalize('t',source).normalized_text)
        self.assertEqual('',disabled.translation_context('primary adosterizm','en','es'))

    def test_environment_patch_switch_does_not_lock_operator_global_rollback(self):
        with patch.dict(os.environ,{'TRAD_GLOSSARY_PATCH':'off'}):
            os.environ.pop('TRAD_GLOSSARY_MODE',None)
            config=replace(GlossaryConfig.from_env(),state_path='')
            controller=RolloutController(config)
            self.assertFalse(config.patch_enabled)
            self.assertFalse(controller.forced)
            self.assertEqual('soft',controller.status()['effective_mode'])
            self.assertEqual('disabled',controller.status()['patch']['state'])
            self.assertEqual('off',controller.change('off',0)['effective_mode'])

    def test_missing_or_corrupt_patch_falls_back_to_working_v2_not_whole_glossary_off(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'manifest.json').write_text('{}')
            config=GlossaryConfig(patch_path=folder,state_path='')
            state=RolloutController(config).status()
            self.assertEqual('soft',state['effective_mode'])
            self.assertEqual('unavailable',state['patch']['state'])
            n=session_normalizer(config,'en',IdentityNormalizer())
            self.assertEqual('primary adosterizm and hypertension',n.normalize('t','primary adosterizm and hyper tension').normalized_text)
            self.assertTrue(n.normalize('t','primary adosterizm').glossary['patch_error'])

    def test_rehashed_package_cannot_enable_a_meaning_changing_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            for name in ['rules.json','manifest.json']:shutil.copyfile(Path(GlossaryConfig.patch_path)/name,p/name)
            rules=json.loads((p/'rules.json').read_text(encoding='utf-8'))
            rules['observed_repairs']=[dict(source='systolic blood pressure',target='diastolic blood pressure')]
            (p/'rules.json').write_text(json.dumps(rules),encoding='utf-8')
            data=(p/'rules.json').read_bytes();manifest=json.loads((p/'manifest.json').read_text(encoding='utf-8'))
            manifest['files'][0].update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            (p/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            with self.assertRaises(ValueError):CorrectionPatch(p,self.release)

    def test_wrong_json_root_types_fail_closed_without_breaking_the_base_glossary(self):
        for value in [[],None,7,'invalid']:
            with self.subTest(value=value),tempfile.TemporaryDirectory() as folder:
                p=Path(folder);(p/'manifest.json').write_text(json.dumps(value),encoding='utf-8')
                n=self.normalizer(patch_path=folder)
                self.assertEqual('hypertension',n.normalize('t','hyper tension').normalized_text)
                self.assertIsNone(n.patch)
                manifest=json.loads((Path(GlossaryConfig.patch_path)/'manifest.json').read_text(encoding='utf-8'))
                data=json.dumps(value).encode('utf-8');(p/'rules.json').write_bytes(data)
                manifest['files'][0].update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
                (p/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
                with self.assertRaises(ValueError):CorrectionPatch(p,self.release)

    def test_wrong_base_manifest_or_bundle_types_restore_legacy_behavior(self):
        for member in ['manifest.json','bundle.json']:
            with self.subTest(member=member),tempfile.TemporaryDirectory() as folder:
                p=Path(folder);data=b'[]'
                if member=='manifest.json':(p/member).write_bytes(data)
                else:
                    manifest=json.loads((Path(GlossaryConfig.release_path)/'manifest.json').read_text(encoding='utf-8'))
                    manifest['files'][0].update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
                    (p/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8');(p/'bundle.json').write_bytes(data)
                config=GlossaryConfig(release_path=folder,state_path='')
                self.assertEqual('off',RolloutController(config).status()['effective_mode'])
                self.assertIsInstance(session_normalizer(config,'en',IdentityNormalizer()),IdentityNormalizer)

    def test_same_words_are_recognized_for_all_66_approved_targets_without_rewriting(self):
        audit=audit_catalog(self.release.concepts,self.release.forms)
        self.assertEqual(657,len(audit['rows']))
        self.assertEqual(66,len(audit['format_recognition']))
        by_id={c['id']:c for c in self.release.concepts}
        for entry in audit['format_recognition']:
            c=by_id[entry['concept_id']];language=entry['language'];canonical=c[language]
            variants=[canonical.replace('-',' '),canonical.replace('-','‐'),canonical.replace('-','‑'),canonical.replace('-','–')]
            for text in variants:
                with self.subTest(id=c['id'],text=text):
                    hits=self.patch.matches(text,language)
                    self.assertTrue(any(h['concept']['id']==c['id'] for h in hits))
                    self.assertTrue(all(text[h['start']:h['end']] for h in hits))
                    if language=='en':
                        self.assertEqual(text,self.normalizer().normalize('t',text).normalized_text)
                    else:
                        self.assertEqual(self.normalizer(enabled=False,language='es').normalize('t',text).normalized_text,
                            self.normalizer(language='es').normalize('t',text).normalized_text)

    def test_longest_non_elevated_phrase_guide_does_not_emit_positive_subphrase(self):
        n=self.normalizer()
        text='No non elevated blood pressure by this test; 5 mg, not 50 mg.'
        self.assertEqual(text,n.normalize('t',text).normalized_text)
        hint=n.translation_context(text,'en','es')
        self.assertIn('non-elevated blood pressure =',hint)
        self.assertNotIn('\nelevated blood pressure =',hint)
        self.assertNotIn('\nblood pressure =',hint)

    def test_existing_acronym_collisions_remain_unexpanded(self):
        audit=audit_catalog(self.release.concepts,self.release.forms)
        self.assertEqual({('en',('mra',)),('es',('eca',))},
            {(c['language'],tuple(c['words'])) for c in audit['lexical_collisions']})
        for language,text in [('en','MRA and HR'),('es','ECA')]:
            self.assertEqual([],self.patch.matches(text,language))
            self.assertFalse(self.patch.scan(text,language)[0])

    def test_format_recognition_cannot_drop_words_numbers_or_identifiers(self):
        n=self.normalizer()
        for text in ['tag_white coat hypertension','tag_x white coat hypertension','white coat hypertension_id',
                     'white, coat hypertension','white 5 coat hypertension','white coated hypertension']:
            self.assertFalse(any(h['concept']['en']=='white-coat hypertension' for h in self.patch.matches(text,'en')))
            self.assertEqual(text,n.normalize('t',text).normalized_text)

    def test_all_657_canonical_english_entries_remain_immutable(self):
        n=self.normalizer()
        for c in self.release.concepts:
            self.assertEqual(c['en'],n.normalize(c['id'],c['en']).normalized_text,c['id'])

    def test_captured_second_reading_repairs_only_observed_spelling_and_reports_resisted(self):
        snapshot=json.loads((ROOT/'benchmarks/glossary_patch_v1/second_reading.json').read_text(encoding='utf-8'))
        rows=[s for e in snapshot['operator_history']['events'] if e['message']['type']=='segmentation'
              for s in e['message']['normalization']['segments']]
        n=self.normalizer();updates=[];reviews=[]
        for row in rows:
            r=n.normalize(row['segment_id'],row['raw_text'])
            if r.normalized_text!=row['normalized_text']:updates.append((row,r))
            reviews.extend(s for s in r.suggestions if s.rule=='medical_context_review_only')
        self.assertEqual(1,len(updates))
        self.assertEqual(updates[0][0]['normalized_text'].replace('adosterizm','aldosteronism'),updates[0][1].normalized_text)
        self.assertEqual(1,len(reviews))

    def test_original_glossaries_and_previous_evidence_hashes_remain_unchanged(self):
        baseline=json.loads((ROOT/'benchmarks/glossary_patch_v1/baseline.json').read_text(encoding='utf-8'))
        for row in baseline['protected_files']:
            self.assertEqual(row['sha256'],hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest(),row['path'])


class CorrectionProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_relay_to_provider_and_overlay_honors_patch_and_both_rollback_switches(self):
        import asyncio
        from websockets.asyncio.server import serve
        from app.asr.whisperlivekit_client import relay
        from app.main import Settings
        from app.overlay.config import CaptionConfig
        from app.overlay.hub import CaptionHub
        from tests.test_proxy import Browser
        raw='No primary adosterizm by this test; keep 5 mg, not 50 mg.'
        bodies=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return b'{"translations":[{"text":"Salida de prueba"}]}'
        def opener(request,timeout):bodies.append(json.loads(request.data));return Response()
        def factory(config,sid,callback):
            return TranslationEngine(config,DeepLTranslatorProvider('test',opener=opener),sid,callback)
        async def wlk(ws):
            await ws.send(json.dumps(dict(type='config',useAudioWorklet=True,mode='full',
                session_language='en',session_language_isolation=1)))
            self.assertEqual(b'',await ws.recv())
            await ws.send(json.dumps(dict(lines=[dict(text=raw,speaker=1)],buffer_transcription='')))
            await ws.send('{"type":"ready_to_stop"}')
        with tempfile.TemporaryDirectory() as folder:
            async with serve(wlk,'127.0.0.1',0) as server:
                for number,(mode,enabled) in enumerate([('soft',True),('soft',False),('shadow',True),('off',True)]):
                    settings=Settings(log_dir=folder,language='en',require_language_ack=True,
                        wlk_url=f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/asr',
                        glossary=GlossaryConfig(mode=mode,patch_enabled=enabled,state_path=''),
                        translation=TranslationConfig(enabled=True,provider='deepl',source_language='en',target_language='es',context_segments=0))
                    browser=Browser();browser.incoming.put_nowait(dict(type='websocket.receive',bytes=b''))
                    sid='patch-pipeline-'+str(number);hub=CaptionHub(CaptionConfig());hub.begin(sid)
                    with patch('app.asr.whisperlivekit_client.build_translation_engine',factory):
                        await asyncio.wait_for(relay(browser,settings,sid,hub),5)
                    result=next(m['translation'] for m in browser.outgoing if m['type']=='translation')
                    expected=raw.replace('adosterizm','aldosteronism') if mode=='soft' and enabled else raw
                    self.assertEqual(raw,result['raw_text'])
                    self.assertEqual(expected,result['normalized_text'])
                    self.assertEqual([expected],bodies[-1]['text'])
                    self.assertEqual('Salida de prueba',hub.caption_history[-1]['text'])
                    self.assertEqual('stopped',browser.outgoing[-1]['state'])
        self.assertIn('aldosteronismo primario',bodies[0]['context'])
        self.assertTrue(all('context' not in body for body in bodies[1:]))

    async def test_actual_deepl_adapter_body_preserves_negations_and_rollback_without_network(self):
        bodies=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return b'{"translations":[{"text":"ok"}]}'
        def opener(request,timeout):bodies.append(json.loads(request.data));return Response()
        raw='No primary adosterizm by this test; keep 5 mg, not 50 mg.'
        for mode,enabled in [('soft',True),('soft',False),('shadow',True),('off',True)]:
            n=CorrectionTests().normalizer(mode,enabled)
            r=n.normalize('t',raw)
            engine=TranslationEngine(TranslationConfig(enabled=True,provider='deepl',source_language='en',target_language='es',context_segments=0),
                DeepLTranslatorProvider('test',opener=opener),mode+str(enabled))
            engine.terminology_context=getattr(n,'translation_context',None)
            await engine.start()
            try:
                request=await engine.submit('t',raw,r.normalized_text)
                await engine.wait_idle()
                self.assertEqual(raw,request.raw_text)
            finally:await engine.close()
        self.assertEqual([raw.replace('adosterizm','aldosteronism')],bodies[0]['text'])
        self.assertIn('aldosteronismo primario',bodies[0]['context'])
        for body in bodies[1:]:
            self.assertEqual([raw],body['text'])
            self.assertNotIn('context',body)


if __name__=='__main__':unittest.main(verbosity=2)
