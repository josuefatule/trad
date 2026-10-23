import random
from pathlib import Path
import sys
import unittest
import wave

import evaluate_trial as trial
from trad_lab.metrics import word_alignment, tokens


class TenTermTrialTests(unittest.TestCase):
    def test_random_draw_reproduces_frozen_selection(self):
        d=trial.load(trial.HERE/'selection.json')
        self.assertEqual(97,d['pool_size'])
        expected=random.Random(d['seed']).sample(sorted(r['concept_id'] for r in d['pool']),10)
        self.assertEqual(expected,[r['concept_id'] for r in d['selected']])
        self.assertEqual(10,len(set(expected)))

    def test_choices_depend_on_calibration_only_and_obey_frozen_tie_break(self):
        for row in trial.load(trial.HERE/'threshold_decisions.json'):
            eligible=[r for r in row['calibration_grid'] if r['negative_triggers']==0]
            best=max(eligible,key=lambda r:(r['recovered'],r['threshold'])) if eligible else None
            self.assertEqual(None if best is None else best['threshold'],row['selected_auto_threshold'])

    def test_checking_never_changes_frozen_thresholds(self):
        choices={r['concept_id']:r['selected_auto_threshold'] for r in trial.load(trial.HERE/'threshold_decisions.json')}
        for r in trial.load(trial.HERE/'synthetic_checking.json'):
            if r['profile']=='individualized':self.assertEqual(choices[r['concept_id']],r['threshold'])

    def test_ref_mapping_handles_insertion_deletion_and_substitution(self):
        a=tokens('a b c');b=tokens('a x b')
        edits=[{'op':'I','ref_index':1,'hyp_index':1},
               {'op':'D','ref_index':2,'hyp_index':3}]
        mapping=trial.ref_map(a,b,edits)
        self.assertEqual({0:0,1:2,2:None},mapping)
        words,indices=trial.extracted_span(1,2,mapping,b,edits)
        self.assertEqual(['x','b'],words)
        substitution=trial.ref_map(a,tokens('a x c'),[{'op':'S','ref_index':1,'hyp_index':1}])
        self.assertEqual({0:0,1:1,2:2},substitution)

    def test_native_window_does_not_recover_all_merged_words(self):
        item={'concept_id':'x','canonical_en':'primary aldosteronism'}
        result=trial.candidate('primaryaldosteronism',[item],{'x':.86})
        self.assertEqual('primaryaldosteronism',result['text'])

    def test_threshold_changes_neighbor_absorption_without_changing_live(self):
        item={'concept_id':'x','canonical_en':'ten-year ASCVD risk'}
        before='the 10-year ASCVD risk'
        low=trial.candidate(before,[item],{'x':.90})
        high=trial.candidate(before,[item],{'x':.94})
        self.assertNotEqual(before,low['text'])
        self.assertEqual(before,high['text'])
        self.assertEqual(before,low['controlled_text'])
        self.assertEqual(before,high['controlled_text'])

    def test_102_real_observations_come_from_34_unique_occurrences(self):
        sources=trial.load(trial.HERE/'reference_occurrences.json')
        self.assertEqual(34,len(sources))
        checked=trial.load(trial.HERE/'real_speech_checking.json')
        for profile in ['raw','uniform_090','individualized']:
            self.assertEqual(102,len([r for r in checked['occurrences'] if r['profile']==profile]))

    def test_no_changes_in_original_glossary_or_prior_evidence(self):
        self.assertTrue(trial.load(trial.HERE/'preservation.json')['original_glossary_package_prior_research_audio_and_asr_unchanged'])
        self.assertFalse(trial.load(trial.HERE/'summary.json')['integration_performed'])

    def test_all_ten_audio_examples_are_exact_source_intervals(self):
        rows=trial.load(trial.HERE/'audio_review_examples.json');self.assertEqual(10,len(rows))
        for row in rows:
            with wave.open(row['source_wav'],'rb') as source:
                source.setpos(row['first_sample']);raw=source.readframes(row['last_sample_exclusive']-row['first_sample'])
            with wave.open(row['path'],'rb') as clip:
                self.assertEqual(raw,clip.readframes(clip.getnframes()))
            self.assertFalse(row['manipulated_prosody'])

    def test_duplicate_checking_inputs_are_disclosed_and_excluded(self):
        d=trial.load(trial.HERE/'checking_overlap_audit.json')
        self.assertTrue(d['exact_duplicate_checking_case_ids'])
        self.assertTrue(d['excluded_from_nonoverlap_summary'])


if __name__=='__main__':
    unittest.main(verbosity=2)
