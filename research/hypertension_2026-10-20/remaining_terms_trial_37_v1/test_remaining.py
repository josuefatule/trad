"""Reproducibility and provenance checks, without asserting a favorable outcome."""
import random
import unittest
from collections import defaultdict
import evaluate_remaining as exp


class RemainingTermTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selection=exp.load(exp.HERE/'selection.json')
        cls.decisions=exp.load(exp.HERE/'threshold_decisions.json')
        cls.corpus=exp.load(exp.HERE/'speech_comparison.json')

    def test_complete_remaining_set_and_seeded_order(self):
        old=exp.load(exp.SIXTY/'selection.json')['selected'];old_ids={r['concept_id'] for r in old}
        expected=sorted([r for r in exp.load(exp.FIFTY/'selection.json')['pool'] if r['concept_id'] not in old_ids],key=lambda r:r['concept_id'])
        random.Random(self.selection['seed']).shuffle(expected)
        self.assertEqual(expected,self.selection['selected'])
        self.assertEqual(37,len(expected));self.assertEqual(97,len(old_ids|{r['concept_id'] for r in expected}))

    def test_previous_sixty_threshold_decisions_are_byte_equivalent_data(self):
        old=exp.load(exp.SIXTY/'thresholds.json')['decisions']
        combined=exp.load(exp.HERE/'combined_thresholds.json')['decisions']
        self.assertEqual(old,combined[:60]);self.assertEqual(self.decisions,combined[60:])

    def test_choices_use_only_constructed_calibration(self):
        for r in self.decisions:
            eligible=[x for x in r['calibration_grid'] if x['negative_triggers']==0]
            best=max(eligible,key=lambda x:(x['recovered'],x['threshold'])) if eligible else None
            expected=best['threshold'] if best and best['recovered'] else None
            self.assertEqual(expected,r['selected_auto_threshold'])
            self.assertFalse(r['operational_approval'])

    def test_no_exact_duplicate_input_label_leaks_between_splits(self):
        cases=exp.load(exp.HERE/'constructed_cases.json')
        keys=[(c['concept_id'],c['positive'],c['text']) for c in cases]
        self.assertEqual(len(keys),len(set(keys)))

    def test_frozen_rules_selection_and_thresholds_are_intact(self):
        protocol=exp.load(exp.HERE/'protocol.json')
        for r in protocol['source_hashes']:self.assertEqual(r['sha256'],exp.sha(exp.ROOT/r['path']))
        self.assertEqual(protocol['selection_sha256'],exp.sha(exp.HERE/'selection.json'))
        self.assertEqual(protocol['variants_sha256'],exp.sha(exp.HERE/'variant_preservation.json'))
        freeze=exp.load(exp.HERE/'threshold_freeze.json')
        self.assertEqual(freeze['decisions_sha256'],exp.sha(exp.HERE/'threshold_decisions.json'))
        self.assertEqual(freeze['combined_sha256'],exp.sha(exp.HERE/'combined_thresholds.json'))

    def test_previous_sixty_corpus_baselines_reproduce(self):
        for model,errors in [('small',131),('medium',107),('large-v3-turbo',131)]:
            r=next(r for r in self.corpus['aggregate'] if r['profile']=='previous60_corrected' and r['model']==model)
            self.assertEqual(errors,r['word_errors']);self.assertEqual(4204,r['reference_words'])

    def test_all_ninety_seven_terms_have_identical_observation_counts(self):
        table=exp.load(exp.HERE/'term_results.json')
        self.assertEqual(97,len({r['concept_id'] for r in table}))
        self.assertEqual(37,sum(r['group']=='new37' for r in table))
        for r in table:
            observations={v['observations'] for v in r['results'].values()}
            self.assertEqual(1,len(observations));self.assertGreater(next(iter(observations)),0)

    def test_protected_corpus_channels_and_number_are_preserved(self):
        for r in self.corpus['rows']:
            self.assertFalse(r['cue_signature_changed']);self.assertFalse(r['function_word_sequence_changed'])
        for c in self.corpus['changes']:
            self.assertFalse(exp.corrected.first.number_changes(c['source'],c['replacement']))

    def test_original_offsets_reconstruct_every_candidate_without_overlap(self):
        grouped=defaultdict(list)
        for c in self.corpus['changes']:grouped[(c['model'],c['sample_id'],c['profile'])].append(c)
        for output in self.corpus['outputs']:
            raw=exp.load(exp.prior.CACHED/'models'/output['model']/output['sample_id']/'result.json')['hypothesis_raw']
            text=raw;changes=sorted(grouped[(output['model'],output['sample_id'],output['profile'])],key=lambda c:c['start'])
            self.assertTrue(all(a['end']<=b['start'] for a,b in zip(changes,changes[1:])))
            for c in reversed(changes):
                self.assertEqual(c['source'],raw[c['start']:c['end']])
                self.assertFalse(any(c['start']<p['end'] and c['end']>p['start'] for p in output['preserved_variants']))
                text=text[:c['start']]+c['replacement']+text[c['end']:]
            self.assertEqual(output['candidate_text'],text)

    def test_context_regression_list_contains_every_new_failure(self):
        previous={r['replay_id']:r for r in exp.load(exp.REFINED/'context_comparison.json')['rows'] if r['profile']=='all_fixes'}
        current=exp.load(exp.HERE/'context_comparison.json')
        expected={r['replay_id'] for r in current['rows'] if r['profile']=='combined97_individualized' and r['group']=='previous60' and previous[r['replay_id']]['passed'] and not r['passed']}
        self.assertEqual(expected,{r['replay_id'] for r in current['previous60_regressions']})

    def test_all_existing_regression_probes_are_retained(self):
        before=exp.load(exp.REFINED/'regression_cases.json')
        current=exp.load(exp.HERE/'previous_regressions_combined97.json')['rows']
        self.assertEqual([r['case_id'] for r in before],[r['case_id'] for r in current])
        self.assertEqual(153,len(current))

    def test_original_and_all_prior_evidence_are_unchanged(self):
        exp.verify_prior()
        self.assertTrue(exp.preservation()['original_and_prior_evidence_unchanged'])
        self.assertEqual('4a4920d3ff9404db5601c1c8f832dde4fdeb180dc95d3f06037576ec726c2896',exp.sha(exp.ROOT/'glossaries/medical_base_en.json'))


if __name__=='__main__':unittest.main(verbosity=2)
