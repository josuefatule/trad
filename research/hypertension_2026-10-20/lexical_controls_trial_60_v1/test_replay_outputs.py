"""Verify frozen inputs, replay invariants and previously observed defects."""
from collections import defaultdict
import unittest
import evaluate_controls as replay
import lab_normalizer as lab

FIRST=replay.HERE
FINAL=FIRST/'boundary_refinement_v2'


class ReplayVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.speech=replay.load(FINAL/'speech_comparison.json')
        cls.context=replay.load(FINAL/'context_comparison.json')

    def test_both_policy_revisions_and_thresholds_remain_frozen(self):
        for r in replay.load(FIRST/'protocol.json')['sources']:
            self.assertEqual(r['sha256'],replay.sha(FIRST/r['name']))
        for r in replay.load(FINAL/'protocol.json')['source_files']:
            self.assertEqual(r['sha256'],replay.sha(FINAL/r['name']))
        for name in ['selection.json','thresholds.json','variant_preservation.json']:
            self.assertEqual((FIRST/name).read_bytes(),(FINAL/name).read_bytes())

    def test_first_replay_evidence_remains_byte_identical(self):
        for r in replay.load(FIRST/'first_replay_manifest.json')['files']:
            self.assertEqual(r['sha256'],replay.sha(FIRST/r['name']))

    def test_old_sixty_and_raw_word_error_baselines_reproduce(self):
        for model,raw,old in [('small',148,136),('medium',117,113),('large-v3-turbo',132,137)]:
            rows={r['profile']:r for r in self.speech['aggregate'] if r['model']==model}
            self.assertEqual(raw,rows['raw']['word_errors'])
            self.assertEqual(old,rows['old60']['word_errors'])
            self.assertEqual(4204,rows['all_fixes']['reference_words'])

    def test_all_sixty_terms_are_observed_in_all_profiles(self):
        terms=replay.load(FINAL/'term_results.json')
        self.assertEqual(60,len({r['concept_id'] for r in terms}))
        self.assertEqual(251,self.speech['unique_reference_occurrences'])
        for r in terms:
            self.assertEqual(6,len(r['results']))
            self.assertGreater(r['results']['all_fixes']['observations'],0)

    def test_corpus_function_words_negations_and_quantities_are_kept(self):
        for r in self.speech['rows']:
            if r['profile']=='all_fixes':
                self.assertFalse(r['cue_signature_changed'])
                self.assertFalse(r['function_word_sequence_changed'])

    def test_no_plural_changes_or_variant_rewrites_in_corpus(self):
        for change in self.speech['changes']:
            if change['profile']!='all_fixes':continue
            self.assertFalse(lab.number_changes(change['source'],change['replacement']))
            output=next(r for r in self.speech['outputs'] if r['model']==change['model'] and
                        r['sample_id']==change['sample_id'] and r['profile']=='all_fixes')
            self.assertFalse(any(change['start']<p['end'] and change['end']>p['start'] for p in output['preserved_variants']))

    def test_corrections_are_disjoint_and_reconstruct_the_saved_output(self):
        grouped=defaultdict(list)
        for c in self.speech['changes']:
            if c['profile']=='all_fixes':grouped[(c['model'],c['sample_id'])].append(c)
        for output in self.speech['outputs']:
            if output['profile']!='all_fixes':continue
            record=replay.load(replay.prior.CACHED/'models'/output['model']/output['sample_id']/'result.json')
            raw=record['hypothesis_raw'];text=raw
            changes=sorted(grouped[(output['model'],output['sample_id'])],key=lambda c:c['start'])
            self.assertTrue(all(a['end']<=b['start'] for a,b in zip(changes,changes[1:])))
            for c in reversed(changes):
                self.assertEqual(c['source'],raw[c['start']:c['end']])
                text=text[:c['start']]+c['replacement']+text[c['end']:]
            self.assertEqual(text,output['candidate_text'])

    def test_original_forty_two_overlap_contexts_are_fixed(self):
        old=replay.load(replay.FIFTY/'context_comparison.json')['rows']
        ids=['fifty:'+r['case_id'] for r in old if r['profile']=='individualized_guarded' and
             r['positive'] and r['calibration_repairable'] and not r['exact_expected_output']]
        self.assertEqual(42,len(ids))
        final={r['replay_id']:r for r in self.context['rows'] if r['profile']=='all_fixes'}
        self.assertTrue(all(final[cid]['passed'] for cid in ids))

    def test_no_previous_context_success_is_lost(self):
        self.assertFalse(self.context['regressed_cases'])
        after=next(r for r in self.context['summary'] if r['profile']=='all_fixes')
        self.assertEqual(0,after['negative_changed'])

    def test_constructed_negatives_and_predeclared_probes_pass(self):
        constructed=replay.load(FINAL/'constructed_comparison.json')['summary']
        self.assertEqual(0,next(r for r in constructed if r['profile']=='all_fixes')['negative_changed'])
        probes=replay.load(FINAL/'regression_comparison.json')['rows']
        after=[r for r in probes if r['profile']=='all_fixes']
        self.assertEqual(153,len(after));self.assertTrue(all(r['passed'] for r in after))

    def test_original_and_all_prior_evidence_hashes_match(self):
        replay.verify_prior()
        preserved=replay.preservation()
        self.assertTrue(preserved['original_and_prior_evidence_unchanged'])
        self.assertEqual('4a4920d3ff9404db5601c1c8f832dde4fdeb180dc95d3f06037576ec726c2896',
                         replay.sha(replay.ROOT/'glossaries/medical_base_en.json'))


if __name__=='__main__':unittest.main(verbosity=2)
