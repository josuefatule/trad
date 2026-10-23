"""Verify integrity and declared protections without requiring better WER."""
from collections import defaultdict
import unittest
import run_flexible as exp
import pressure_guard as guard


class OutputVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.corpus=exp.load(exp.HERE/'speech_comparison.json')

    def test_frozen_code_and_inputs_unchanged(self):
        protocol=exp.load(exp.HERE/'protocol.json')
        for row in protocol['source_hashes']:self.assertEqual(row['sha256'],exp.sha(exp.ROOT/row['path']))
        for row in protocol['frozen_data']:self.assertEqual(row['sha256'],exp.sha(exp.HERE/row['name']))

    def test_same_97_terms_and_17_exact_only(self):
        selected,profiles,_=exp.inputs()
        self.assertEqual(97,len({r['concept_id'] for r in selected}))
        before=profiles['previous97']
        for profile in exp.PROFILES:
            self.assertEqual(17,sum(t is None for t in profiles[profile].values()))
            for cid,t in profiles[profile].items():
                if before[cid] is None:self.assertIsNone(t)
                elif profile in exp.CAPS:self.assertEqual(min(before[cid],exp.CAPS[profile]),t)

    def test_baseline_reproduces_word_errors(self):
        for model,value in [('small',131),('medium',100),('large-v3-turbo',131)]:
            row=next(r for r in self.corpus['aggregate'] if r['model']==model and r['profile']=='previous97')
            self.assertEqual(value,row['word_errors']);self.assertEqual(4204,row['reference_words'])

    def test_all_profiles_cover_every_term_and_recording(self):
        self.assertEqual(63,len(self.corpus['rows']))
        self.assertEqual(310,self.corpus['unique_reference_occurrences'])
        table=exp.load(exp.HERE/'term_results.json')
        self.assertEqual(97,len(table))
        for r in table:
            self.assertEqual(7,len(r['results']))
            self.assertEqual(1,len({v['observations'] for v in r['results'].values()}))

    def test_new_pressure_controls_have_no_negative_rewrites(self):
        data=exp.load(exp.HERE/'pressure_comparison.json')
        for row in data['rows']:
            if row['profile'].startswith('direction_guard') and not row['positive']:
                self.assertFalse(row['negative_changed'])

    def test_every_new_corpus_change_preserves_proven_direction(self):
        for c in self.corpus['changes']:
            if c['profile'].startswith('direction_guard'):
                verdict=guard.direction_verdict(c['source'],c['replacement'])
                self.assertTrue(verdict['accepted'],c)

    def test_function_words_negations_quantities_and_number_are_preserved(self):
        for row in self.corpus['rows']:
            self.assertFalse(row['cue_signature_changed']);self.assertFalse(row['function_word_sequence_changed'])
        for c in self.corpus['changes']:
            self.assertFalse(guard.previous.first.number_changes(c['source'],c['replacement']))

    def test_disjoint_original_offsets_reconstruct_every_saved_output(self):
        groups=defaultdict(list)
        for c in self.corpus['changes']:groups[(c['model'],c['sample_id'],c['profile'])].append(c)
        for output in self.corpus['outputs']:
            raw=exp.load(exp.old.prior.CACHED/'models'/output['model']/output['sample_id']/'result.json')['hypothesis_raw']
            changes=sorted(groups[(output['model'],output['sample_id'],output['profile'])],key=lambda c:c['start']);text=raw
            self.assertTrue(all(a['end']<=b['start'] for a,b in zip(changes,changes[1:])))
            for c in reversed(changes):
                self.assertEqual(c['source'],raw[c['start']:c['end']])
                self.assertFalse(any(c['start']<p['end'] and c['end']>p['start'] for p in output['preserved_variants']))
                text=text[:c['start']]+c['replacement']+text[c['end']:]
            self.assertEqual(output['candidate_text'],text)

    def test_dataset_transitions_report_every_loss_and_gain(self):
        for name in ['pressure','constructed','context','regression']:
            d=exp.load(exp.HERE/(name+'_comparison.json'))
            before={r['case_id']:r for r in d['rows'] if r['profile']=='previous97'}
            for transition in d['transitions']:
                rows=[r for r in d['rows'] if r['profile']==transition['profile']]
                lost={r['case_id'] for r in rows if before[r['case_id']]['passed'] and not r['passed']}
                self.assertEqual(lost,set(transition['regressed_case_ids']))

    def test_original_and_all_previous_evidence_are_unchanged(self):
        exp.verify_prior()
        self.assertTrue(exp.preserve()['original_and_prior_evidence_unchanged'])
        self.assertEqual('4a4920d3ff9404db5601c1c8f832dde4fdeb180dc95d3f06037576ec726c2896',exp.sha(exp.ROOT/'glossaries/medical_base_en.json'))


if __name__=='__main__':unittest.main(verbosity=2)
