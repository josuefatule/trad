"""Protocol and algorithm invariants, independent of model text quality."""
import unittest
import numpy as np
from trad_lab.m4c.incremental import Config, HorizonError, Incremental, Word


class IncrementalTests(unittest.TestCase):
    def engine(self, hypotheses, config=Config(window_s=5,update_s=1)):
        self.events=[];self.inputs=[]
        def decode(audio,start):
            self.inputs.append((audio.copy(),start))
            return hypotheses.pop(0)
        return Incremental(decode,self.events.append,config)

    def push(self,e,n=1):
        for _ in range(n):e.push(np.zeros(16000,dtype='float32'))

    def test_only_available_pcm_and_no_alias(self):
        e=self.engine([[],[]]);block=np.arange(16000,dtype='float32')
        e.push(block);block[:]=-1;self.push(e)
        np.testing.assert_array_equal(self.inputs[0][0],np.arange(16000,dtype='float32'))
        self.assertEqual([len(a) for a,_ in self.inputs],[16000,32000])

    def test_negation_cannot_be_confirmed_by_changed_word(self):
        e=self.engine([[Word(' no',.1,.3)],[Word(' not',.1,.3)],[Word(' not',.1,.3)]])
        self.push(e,3)
        self.assertEqual([w['text'] for v in self.events for w in v['confirmed']],[' not'])

    def test_repeated_words_keep_distinct_time_occurrences(self):
        first=Word(' no',.1,.3);second=Word(' no',1.1,1.3)
        e=self.engine([[first],[first,second],[first,second],[first,second]])
        self.push(e,4)
        self.assertEqual([w['start'] for v in self.events for w in v['confirmed']],[.1,1.1])

    def test_confirmed_words_never_revised(self):
        e=self.engine([[Word(' 120',.1,.3)],[Word(' 120',.1,.3)],[Word(' 130',.1,.3)]])
        self.push(e,3)
        self.assertEqual([w['text'] for v in self.events for w in v['confirmed']],[' 120'])

    def test_end_does_not_force_unstable_tail_or_duplicate_vote(self):
        e=self.engine([[Word(' hypertension',.1,.3)]])
        self.push(e);r=e.finish()
        self.assertEqual(r['committed_words'],0)
        self.assertEqual(r['unconfirmed_tail_words'],1)
        self.assertEqual(len(self.inputs),1)
        with self.assertRaises(RuntimeError):e.finish()
        with self.assertRaises(RuntimeError):self.push(e)

    def test_resegmented_committed_term_is_not_appended_again(self):
        term=Word(' hypertension',.1,.7)
        changed=[Word(' high',.1,.4),Word(' attention',.4,.9),Word(' next',1.1,1.3)]
        e=self.engine([[term],[term],changed,changed])
        self.push(e,4)
        self.assertEqual([w['text'] for v in self.events for w in v['confirmed']],[' hypertension',' next'])
        self.assertTrue(self.events[2]['boundary_conflicts'])

    def test_fast_repeated_word_is_not_deduplicated_without_overlap(self):
        a=Word(' no',.1,.3);b=Word(' no',.35,.55)
        e=self.engine([[a],[a],[b],[b]])
        self.push(e,4)
        self.assertEqual([w['start'] for v in self.events for w in v['confirmed']],[.1,.35])

    def test_partial_medical_word_is_not_committed_separately(self):
        a=[Word(' norma',.1,.3),Word('-tensive',.3,.5)]
        b=[Word(' norma',.1,.3),Word('-attensive',.3,.5)]
        e=self.engine([a,b,b]);self.push(e,2)
        self.assertEqual(e.committed_count,0)
        self.push(e)
        self.assertEqual([w['text'] for v in self.events for w in v['confirmed']],[' norma-attensive'])
        self.assertEqual(len(self.events[0]['decoder_words']),2)

    def test_medical_signs_units_and_comparators_require_agreement(self):
        for a,b in [('-5','5'),('5%','5'),('<120','120'),('mg/ml','mg ml'),('120-139','120 139')]:
            with self.subTest(a=a,b=b):
                e=self.engine([[Word(' '+a,.1,.3)],[Word(' '+b,.1,.3)]])
                self.push(e,2);self.assertEqual(e.committed_count,0)

    def test_expanded_percent_does_not_duplicate_a_confirmed_unit(self):
        a=Word(' 10%',.1,.6)
        b=[Word(' 10',.1,.3),Word(' percent',.3,.65),Word(' risk',.9,1.2)]
        e=self.engine([[a],[a],b,b]);self.push(e,4)
        self.assertEqual([w['text'] for v in self.events for w in v['confirmed']],[' 10%',' risk'])

    def test_separate_numeric_minus_is_never_dropped_as_punctuation(self):
        words=[Word(' -',.1,.2),Word(' 5',.2,.4),Word(' mg',.4,.6)]
        e=self.engine([words,words]);self.push(e,2)
        self.assertEqual(''.join(w['text'] for v in self.events for w in v['confirmed']),' - 5 mg')

    def test_missing_prefix_fails_instead_of_disappearing(self):
        e=self.engine([[Word(' no',0,.5)],[],[],[],[],[]])
        self.push(e)
        # Deliberately keep an unconfirmed prefix at the horizon.
        e.audio=np.zeros(80000,dtype='float32');e.received=e.decoded=80000
        with self.assertRaises(HorizonError):self.push(e)
        with self.assertRaises(RuntimeError):self.push(e)
        with self.assertRaises(RuntimeError):e.finish()

    def test_silence_memory_is_bounded_on_long_stream(self):
        e=Incremental(lambda a,s:[],lambda v:None,Config(window_s=5,update_s=1))
        self.push(e,1000)
        self.assertEqual(e.peak_samples,80000)
        self.assertLessEqual(len(e.recent),32)
        self.assertEqual(e.pending,[])

    def test_adaptive_trims_only_confirmed_boundaries_and_keeps_order(self):
        events=[]
        def decode(audio,start):
            end=start+len(audio)/16000
            return [Word(' word'+str(i)+('.' if i%4==3 else ''),i+.1,i+.3)
                    for i in range(int(start),int(end)) if i+.1>=start]
        e=Incremental(decode,events.append,Config(window_s=5,update_s=1,mode='adaptive',max_buffer_s=10))
        self.push(e,40);e.finish()
        words=[w['text'] for v in events for w in v.get('confirmed',[])]
        self.assertEqual(words,[' word'+str(i)+('.' if i%4==3 else '') for i in range(39)])
        self.assertLessEqual(e.peak_samples,160001)
        self.assertTrue(any(v.get('trim') for v in events))

    def test_adaptive_long_preroll_keeps_first_unconfirmed_word(self):
        events=[]
        def decode(audio,start):
            end=start+len(audio)/16000
            return [Word(' no',28,29.5)] if start<=28 and end>=30 else []
        e=Incremental(decode,events.append,Config(window_s=15,update_s=1,mode='adaptive',minimum_age_s=4))
        self.push(e,45);e.finish()
        self.assertEqual([w['text'] for v in events for w in v.get('confirmed',[])],[' no'])
        self.assertLessEqual(e.peak_samples,480001)
        self.assertTrue(any((v.get('trim') or {}).get('reason')=='before_provisional_or_empty_hypothesis' for v in events))

    def test_adaptive_long_empty_pause_stays_bounded(self):
        e=Incremental(lambda a,s:[],lambda v:None,Config(window_s=5,update_s=1,mode='adaptive',max_buffer_s=10))
        self.push(e,1000);e.finish()
        self.assertLessEqual(e.peak_samples,160001)

    def test_adaptive_preroll_fix_never_discards_old_unstable_negation(self):
        calls=0
        def decode(audio,start):
            nonlocal calls
            calls+=1
            return [Word(' no' if calls%2 else ' not',.1,.3)]
        e=Incremental(decode,lambda v:None,Config(window_s=5,update_s=1,mode='adaptive',max_buffer_s=10))
        with self.assertRaises(HorizonError):self.push(e,11)
        self.assertEqual(e.committed_count,0)

    def test_reject_nonfinite_multichannel_and_future_word(self):
        e=self.engine([[Word(' future',1,2)]])
        with self.assertRaises(ValueError):e.push(np.array([np.nan],dtype='float32'))
        with self.assertRaises(ValueError):e.push(np.zeros((2,4),dtype='float32'))
        with self.assertRaises(ValueError):self.push(e)

    def test_three_votes_are_three_distinct_availabilities(self):
        w=Word(' 70',.1,.3)
        e=self.engine([[w],[w],[w]],Config(window_s=5,update_s=1,agreement=3))
        self.push(e,2);self.assertEqual(e.committed_count,0)
        self.push(e);self.assertEqual(e.committed_count,1)


if __name__=='__main__':unittest.main()
