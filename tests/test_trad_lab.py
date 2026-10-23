import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trad_lab.metrics import tokens, edit_distance, word_alignment, metrics, term_inventory
from trad_lab.glossary import audit, shadow
from trad_lab.audio import corpus_pairs
from trad_lab.streaming import analyze_capture
from trad_lab.safety import LiveGuard
from trad_lab.runner import DECODE, save, verify_completed


class LabMetricTests(unittest.TestCase):
    def test_bit_vector_matches_independent_dp_exhaustively(self):
        values=[''.join(v) for n in range(5) for v in itertools.product('ab',repeat=n)]
        for a in values:
            for b in values:
                row=list(range(len(b)+1))
                for i,x in enumerate(a,1):
                    nxt=[i]
                    for j,y in enumerate(b,1):nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
                    row=nxt
                self.assertEqual(edit_distance(a,b),row[-1],(a,b))

    def test_known_alignment_insertions_can_exceed_one_empty_and_unicode(self):
        r=metrics('no edema 5 mg','edema 50 mg now')
        self.assertEqual(r['word_errors'],3)
        self.assertEqual(r['wer'],.75)
        self.assertTrue(r['risk_flag_counts']['negation_cue'])
        self.assertEqual(metrics('a','x y z')['wer'],3.)
        self.assertIsNone(metrics('','word')['wer'])
        self.assertEqual(metrics('','')['cer'],0)
        self.assertEqual(tokens('Heart-failure: 120/80, 3.5 mg; DON’T'),['heart','failure','120/80','3.5','mg',"don't"])

    def test_medical_terms_alias_counts_do_not_rewrite_text(self):
        t=[{'canonical':'blood pressure','aliases':['BP']}]
        row=term_inventory('blood pressure and BP','blood pressure',t)[0]
        self.assertEqual(row['occurrence_deficit'],1)


class LabGlossaryTests(unittest.TestCase):
    def test_exact_099_not_safety_and_controlled_rejects_medical_rewrites(self):
        doc={'terms':[{'canonical':'positive','aliases':['negative'],'auto_apply':'exact','auto_threshold':.99,'suggest_threshold':.98}]}
        result=shadow('negative','negative',doc,'s')
        self.assertEqual(result['candidate_text'],'positive')
        self.assertEqual(result['controlled_text'],'negative')
        self.assertIn('clinical_polarity_or_laterality_cue',result['corrections'][0]['risk_categories'])

    def test_collisions_block_loader_and_threshold_boost_is_explicit(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'logs') as tmp:
            path=Path(tmp)/'glossary.json'
            path.write_text(json.dumps({'terms':[{'canonical':'one','aliases':['same']},{'canonical':'two','aliases':['same']}]}))
            report=audit(path)
            self.assertFalse(report['schema_compatible'])
            self.assertEqual(len(report['exact_collisions']),1)
            self.assertEqual(report['threshold_099_demo']['output'],'hypertension')
            self.assertLess(report['threshold_099_demo']['uncalibrated_score_before_boost'],.99)
            self.assertEqual(report['threshold_099_demo']['corrections'][0]['confidence'],.99)

    def test_invalid_thresholds_and_suggest_only(self):
        result=shadow('BP','BP',{'terms':[{'canonical':'blood pressure','aliases':['BP'],'auto_apply':'suggest'}]},'s')
        self.assertEqual(result['candidate_text'],'BP')
        self.assertTrue(result['suggestions'])
        bad=shadow('x','x',{'terms':[{'canonical':'x','auto_threshold':.8,'suggest_threshold':.9}]},'s')
        self.assertEqual(bad['status'],'blocked')


class LabInputTests(unittest.TestCase):
    def test_resume_rejects_changed_hypothesis_profile_or_missing_sample(self):
        from trad_lab.audio import digest
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'logs') as tmp:
            folder=Path(tmp);sample=folder/'sample';sample.mkdir()
            (sample/'reference.original.txt').write_bytes(b'original')
            (sample/'hypothesis.raw.txt').write_text('hypothesis',encoding='utf-8')
            options={**DECODE,'initial_prompt':None,'hotwords':None}
            env={'model':'small','decoding':options,'device':'cuda:0','compute_type':'float16'}
            save(folder/'environment.json',env)
            inputs=[{'id':'sample','audio_sha256':'audio-hash','reference_sha256':digest(sample/'reference.original.txt'),'reference_raw':'original'}]
            save(sample/'result.json',{'model':'small','variant':'baseline',**inputs[0],
                'hypothesis_raw':'hypothesis','decoding':options})
            verify_completed(folder,inputs,'small',False)
            (sample/'hypothesis.raw.txt').write_text('changed',encoding='utf-8')
            with self.assertRaises(ValueError):verify_completed(folder,inputs,'small',False)
            (sample/'hypothesis.raw.txt').write_text('hypothesis',encoding='utf-8')
            env['compute_type']='int8';save(folder/'environment.json',env)
            with self.assertRaises(ValueError):verify_completed(folder,inputs,'small',False)
            env['compute_type']='float16';save(folder/'environment.json',env)
            with self.assertRaises(ValueError):verify_completed(folder,inputs+[{'id':'missing'}],'small',False)

    def test_pairs_hashes_preserved_and_ambiguous_inputs_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'logs') as tmp:
            folder=Path(tmp)/'sample';folder.mkdir()
            audio=folder/'a.mp3';audio.write_bytes(b'unchanged')
            ref=folder/'r.txt';ref.write_text('original')
            rows=corpus_pairs(tmp)
            self.assertEqual(rows[0]['id'],'sample')
            self.assertEqual(audio.read_bytes(),b'unchanged')
            (folder/'extra.txt').write_text('x')
            with self.assertRaises(ValueError):corpus_pairs(tmp)


class LabSafetyAndStreamingTests(unittest.TestCase):
    def test_live_guard_caches_token_and_blocks_active_or_unknown(self):
        class Response:
            def __init__(self,data):self.raw=json.dumps(data).encode()
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return self.raw
        state={'state':'live','session_open':True};calls=[]
        def opened(req,timeout):
            url=req if isinstance(req,str) else req.full_url;calls.append(url)
            if url.endswith('/health'):return Response({'status':'ok'})
            if url.endswith('/bootstrap'):return Response({'control_token':'test-only'})
            return Response(state)
        guard=LiveGuard()
        with patch('trad_lab.safety.urllib.request.urlopen',opened):
            self.assertFalse(guard.check()['safe']);self.assertFalse(guard.check()['safe'])
            self.assertEqual(sum(x.endswith('/bootstrap') for x in calls),1)
            state.update(state='stopped',session_open=False)
            self.assertTrue(guard.check()['safe'])
            state.update(state='unexpected')
            self.assertFalse(guard.check()['safe'])

    def test_streaming_pre_post_actual_ready_and_handshake_required(self):
        sid='lab';config={'type':'config','session_id':sid,'direction':{'source_language':'en'},
            'capabilities':dict.fromkeys(['operator_console','operator_recovery','session_direction','captions_clear'],1),
            'wlk':{'session_language_isolation':1,'session_language':'en','mode':'full','useAudioWorklet':True}}
        records=[{'at':0,'message':config},{'at':1,'message':{'type':'asr','session_id':sid,
            'payload':{'lines':[{'speaker':1,'text':'No edema.'}],'buffer_transcription':''},
            'segmentation':{'ready_segments':[{'id':sid+':1','text':'No edema.'}]}}},
            {'at':2,'message':{'type':'status','state':'stopped','session_id':sid}}]
        result=analyze_capture(records,'No edema.')
        self.assertEqual(result['raw_vs_ready']['wer'],0)
        self.assertEqual(result['raw_metrics']['wer'],0)
        config['wlk']['session_language']='es'
        with self.assertRaises(ValueError):analyze_capture(records,'No edema.')

    def test_mixed_session_not_merged_and_empty_fragment_not_invented(self):
        with self.assertRaises(ValueError):analyze_capture([],None)

    def test_dose_context_is_review_flag_not_automatic_correction(self):
        result=metrics('dose five mg daily','dose fifty mg daily')
        self.assertTrue(result['risk_flag_counts']['dose_or_measurement_context'])
        self.assertEqual(result['hypothesis_normalized'],'dose fifty mg daily')

    def test_raw_measurement_channel_exposes_signs_hidden_by_lexical_wer(self):
        result=metrics('change -5 mg and <10%','change 5 mg and 10%')
        self.assertEqual(result['wer'],0)
        self.assertTrue(result['measurement_signature_review']['changed'])
        self.assertEqual([x['value'] for x in result['measurement_signature_review']['reference']],['-5mg','<10%'])
