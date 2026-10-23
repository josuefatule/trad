import random
import unittest
import evaluate_50 as exp


class FiftyTermTests(unittest.TestCase):
    def test_uniform_random_draw_reproduces_all_fifty(self):
        s=exp.prior.load(exp.HERE/'selection.json')
        self.assertEqual(87,s['pool_size'])
        expected=random.Random(s['seed']).sample(sorted(r['concept_id'] for r in s['pool']),50)
        self.assertEqual(expected,[r['concept_id'] for r in s['selected']])

    def test_all_fifty_are_new_relative_to_first_ten(self):
        selected=exp.prior.load(exp.HERE/'selection.json')['selected']
        old=exp.prior.load(exp.TEN/'selection.json')['selected']
        self.assertEqual(50,len({r['concept_id'] for r in selected}))
        self.assertFalse({r['concept_id'] for r in selected}&{r['concept_id'] for r in old})

    def test_no_identical_input_label_leaks_between_constructed_splits(self):
        cases=exp.prior.load(exp.HERE/'constructed_cases.json')
        keys=[(r['concept_id'],r['positive'],r['text']) for r in cases]
        self.assertEqual(len(keys),len(set(keys)))

    def test_choices_follow_only_guarded_calibration_and_fixed_tie_break(self):
        for r in exp.prior.load(exp.HERE/'threshold_decisions.json'):
            eligible=[x for x in r['calibration_grid'] if x['negative_triggers']==0]
            best=max(eligible,key=lambda x:(x['recovered'],x['threshold'])) if eligible else None
            expected=best['threshold'] if best and best['recovered'] else None
            self.assertEqual(expected,r['selected_auto_threshold'])
            self.assertFalse(r['operational_approval'])

    def test_no_useful_recovery_means_exact_only(self):
        rows=exp.prior.load(exp.HERE/'threshold_decisions.json')
        off=[r for r in rows if r['selected_auto_threshold'] is None]
        self.assertTrue(off)
        for r in off:self.assertEqual('exact_only_no_useful_guarded_fuzzy_recovery',r['mode'])

    def test_threshold_choices_frozen_before_checking(self):
        freeze=exp.prior.load(exp.HERE/'threshold_freeze.json')
        self.assertTrue(freeze['calibration_only'])
        self.assertEqual(freeze['decisions_sha256'],exp.prior.sha(exp.HERE/'threshold_decisions.json'))

    def test_context_guard_source_is_not_retuned(self):
        protocol=exp.prior.load(exp.HERE/'protocol.json')
        expected=next(r['sha256'] for r in protocol['inputs'] if r['path'].endswith('context_boundary_trial_10_v1/evaluate_context.py'))
        self.assertEqual(expected,exp.prior.sha(exp.GUARD/'evaluate_context.py'))

    def test_prior_raw_and_ten_term_baselines_reproduce(self):
        data=exp.prior.load(exp.HERE/'speech_comparison.json')
        expected={'small':(148,132),'medium':(117,109),'large-v3-turbo':(132,132)}
        for model,(raw,old) in expected.items():
            self.assertEqual(raw,next(r['word_errors'] for r in data['aggregate'] if r['model']==model and r['profile']=='raw'))
            self.assertEqual(old,next(r['word_errors'] for r in data['aggregate'] if r['model']==model and r['profile']=='previous10_guarded'))

    def test_each_new_term_is_present_in_every_speech_comparison(self):
        terms=exp.prior.load(exp.HERE/'term_results.json')
        self.assertEqual(50,len(terms))
        for r in terms:
            self.assertGreater(r['results']['raw']['observations'],0)
            self.assertEqual(6,len(r['results']))
            self.assertFalse(r['operational_approval'])

    def test_guarded_outputs_preserve_function_words_negations_and_quantities(self):
        rows=exp.prior.load(exp.HERE/'speech_comparison.json')['rows']
        for r in rows:
            if r['profile'] in ['new50_uniform090_guarded','new50_individualized_guarded','combined60_individualized_guarded']:
                self.assertFalse(r['cue_signature_changed'])
                self.assertFalse(r['function_word_sequence_changed'])

    def test_previous_by_correction_remains_local(self):
        old=exp.prior.load(exp.TEN/'selection.json')['selected']
        thresholds={r['concept_id']:r['selected_auto_threshold'] for r in exp.prior.load(exp.TEN/'threshold_decisions.json')}
        text='primary allosteronism by this test'
        self.assertEqual('primary aldosteronism by this test',exp.ctx.candidate(text,old,thresholds)['text'])

    def test_controlled_text_is_never_the_simulated_candidate(self):
        item={'concept_id':'x','canonical_en':'primary aldosteronism'}
        source='No primary allosteronism by this test; 5 mg.'
        result=exp.ctx.candidate(source,[item],{'x':.94})
        self.assertEqual(source,result['controlled_text'])
        self.assertEqual('No primary aldosteronism by this test; 5 mg.',result['text'])


if __name__=='__main__':unittest.main(verbosity=2)
