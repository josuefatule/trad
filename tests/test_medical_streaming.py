from dataclasses import replace
import json
from pathlib import Path
import unittest

from app.captions.identity_normalizer import IdentityNormalizer
from app.captions.segment_manager import SegmentConfig, SegmentManager
from app.captions.transcript_state import TranscriptState
from app.terminology.rollout import GlossaryConfig, session_normalizer
from app.terminology.streaming_policy import MedicalBoundaries, MedicalSegmentManager, session_segment_manager
from benchmarks.replay_reading_soft_v2 import captured_reading, replay


class MedicalStreamingTests(unittest.TestCase):
    def normalizer(self,mode='soft'):
        return session_normalizer(GlossaryConfig(mode=mode,state_path=''),'en',IdentityNormalizer())

    def test_pressure_joins_preserve_direction_case_numbers_negation_and_by(self):
        cases={
            'Hyper tension and hypo tension.':'Hypertension and hypotension.',
            'HYPER TENSION; HYPO TENSION.':'HYPERTENSION; HYPOTENSION.',
            'No hyper tension by this test; 5 mg, not 15 mg.':'No hypertension by this test; 5 mg, not 15 mg.',
        }
        for source,expected in cases.items():
            result=self.normalizer().normalize('t',source)
            self.assertEqual(expected,result.normalized_text)
            self.assertEqual(source,result.raw_text)
            for c in result.corrections:self.assertEqual(c.source,source[c.start:c.end])
        for source in ['hypetension','hypo, tension','hyper, tension','tag_hyper tension',
                       'hyper tension_x','tag_primary hyper tension','non-hyper tension',"hyper tension's",'high rate',
                       'the astolic blood pressure','primary outlawed','5 mg, not 15 mg']:
            self.assertEqual(source,self.normalizer().normalize('t',source).normalized_text,source)

    def test_off_and_shadow_restore_segmentation_and_text(self):
        text='hyper tension and hypo tension.'
        for mode in ['off','shadow']:
            n=self.normalizer(mode)
            self.assertIs(type(session_segment_manager(n,None,'t')),SegmentManager)
            self.assertEqual(text,n.normalize('t',text).normalized_text)
        self.assertEqual(2,len(self.normalizer('shadow').normalize('t',text).suggestions))
        self.assertIsInstance(session_segment_manager(self.normalizer(),None,'t'),MedicalSegmentManager)

    def test_all_boundaries_inside_known_expressions_and_connectors_are_blocked(self):
        policy=MedicalBoundaries(self.normalizer().release,'en')
        for left,right in [('orthostatic','hypotension.'),('physical','inactivity.'),
                           ('shortness of','breath.'),('hyper','tension.'),('10 mm of','mercury.')]:
            text='The report mentions '+left+' '+right
            self.assertFalse(policy.allowed(text,len('The report mentions '+left)),text)
            self.assertTrue(policy.allowed(text,len(text)),text)
        self.assertFalse(policy.allowed('The report states there is no',len('The report states there is no')))

    def test_incomplete_term_wait_is_bounded_and_eof_does_not_lose_words(self):
        n=self.normalizer();m=session_segment_manager(n,None,'grace');s=TranscriptState()
        text='The second patient has orthostatic'
        s.update(dict(lines=[dict(text=text,speaker=1)]));m.update(s,0)
        self.assertFalse(m.tick(5.5).ready_segments)
        result=m.tick(7.1)
        self.assertEqual([text],[r.text for r in result.ready_segments])
        self.assertTrue(any(e['type']=='medical_boundary_bypass' for e in result.events))
        self.assertFalse(m.finish(7.2).ready_segments)
        m=session_segment_manager(n,None,'eof');m.update(s,0)
        self.assertEqual([text],[r.text for r in m.finish(.1).ready_segments])

    def test_continuation_within_grace_keeps_medical_term_whole(self):
        n=self.normalizer();m=session_segment_manager(n,None,'continue');s=TranscriptState()
        s.update(dict(lines=[dict(text='The second patient has orthostatic',speaker=1)]));m.update(s,0)
        self.assertFalse(m.tick(5.5).ready_segments)
        s.update(dict(lines=[dict(text='The second patient has orthostatic hypotension.',speaker=1)]));updated=m.update(s,5.6)
        result=m.tick(6.5)
        self.assertEqual(['The second patient has orthostatic hypotension.'],[r.text for r in (*updated.ready_segments,*result.ready_segments)])

    def test_long_unpunctuated_speech_remains_bounded_without_loss_or_duplication(self):
        n=self.normalizer();m=session_segment_manager(n,None,'bounds');s=TranscriptState()
        text=' '.join(['blood pressure and physical inactivity']*30)
        s.update(dict(lines=[dict(text=text,speaker=1)]));rows=list(m.update(s,0).ready_segments)
        rows+=list(m.finish(.1).ready_segments)
        self.assertEqual(text.split(),' '.join(r.text for r in rows).split())
        self.assertTrue(all(r.word_count<=m.config.max_words for r in rows[:-1]))

    def test_same_user_reading_at_recorded_release_times(self):
        captured=captured_reading()
        result=replay([(s['emitted_at'],s['text']) for s in captured],'soft')
        self.assertEqual(3,result['corrections'])
        self.assertEqual([],result['split_phrases'])
        self.assertIn('5 mg, not 15 mg',result['normalized'])
        self.assertLess(result['segments'],len(captured))

    def test_full_recorded_asr_stream_preserves_words_and_late_punctuation(self):
        from benchmarks.segment_latency_ab import load_fixture,final_words
        from replay_fixture import replay as replay_snapshots
        normalizer=session_normalizer(GlossaryConfig(state_path=''),'es',IdentityNormalizer())
        fixture=load_fixture(Path(__file__).resolve().parents[1]/'benchmarks/medical_full_receive.json.gz')
        results=list(replay_snapshots(fixture['events'],session_segment_manager(normalizer,None,'full-stream')))
        rows=[s for _,r in results for s in r.ready_segments]
        self.assertEqual(final_words(fixture['events']),' '.join(s.text for s in rows).split())
        self.assertFalse([e for _,r in results for e in r.events if e['type']=='late_revision_detected'])


if __name__=='__main__':unittest.main()
