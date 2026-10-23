import unittest
import lab_normalizer as lab
import evaluate_controls as replay


class LaboratoryPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selected,cls.thresholds,cls.variants=replay.inputs()

    def candidate(self,text,profile='all_fixes'):
        return lab.candidate(text,self.selected,self.thresholds,self.variants,profile)

    def test_same_sixty_and_unchanged_thresholds(self):
        old=replay.load(replay.TEN/'selection.json')['selected']+replay.load(replay.FIFTY/'selection.json')['selected']
        decisions=replay.load(replay.TEN/'threshold_decisions.json')+replay.load(replay.FIFTY/'threshold_decisions.json')
        self.assertEqual(old,self.selected)
        self.assertEqual({r['concept_id']:r['selected_auto_threshold'] for r in decisions},self.thresholds)

    def test_registered_forms_are_preserved_in_context_without_expansion(self):
        for r in self.variants:
            text='No evidence of '+r['form']+' by this test; ≥5 mg.'
            with self.subTest(form=r['form']):self.assertEqual(text,self.candidate(text)['text'])

    def test_pharmacologic_variant_survives_alongside_a_real_typo(self):
        text='pharmacologic therapy with urinary allosterone by this test'
        expected='pharmacologic therapy with urinary aldosterone by this test'
        self.assertEqual(expected,self.candidate(text)['text'])

    def test_observed_plural_failures_are_preserved(self):
        for text in ['diastolic blood pressures','cardiovascular risks','No diastolic blood pressures by this test; ≥5 mg.']:
            with self.subTest(text=text):self.assertEqual(text,self.candidate(text)['text'])

    def test_number_changes_are_blocked_in_both_directions(self):
        for source,canonical in [('cardiovascular risks','cardiovascular risk'),('cardiovascular risk','cardiovascular risks'),
                                 ('physical activities','physical activity'),('physical activity','physical activities'),
                                 ('clinical diagnoses','clinical diagnosis'),('clinical diagnosis','clinical diagnoses')]:
            selected=[dict(concept_id='test',canonical_en=canonical)]
            result=lab.candidate(source,selected,{'test':.90},[])
            with self.subTest(source=source,canonical=canonical):self.assertEqual(source,result['text'])

    def test_plural_guard_does_not_rewrite_another_typo_to_singular(self):
        text='diastolic bloood pressures'
        self.assertEqual(text,self.candidate(text)['text'])

    def test_all_six_known_overlaps_are_repaired(self):
        for r in replay.load(replay.FIFTY/'overlap_diagnostics.json'):
            result=self.candidate(r['input'])
            with self.subTest(term=r['canonical_en']):
                self.assertEqual(r['expected'],result['text'])
                self.assertTrue(result['overlap_resolutions'])

    def test_long_canonical_remains_intact(self):
        for row in self.selected:
            text=row['canonical_en']
            with self.subTest(text=text):self.assertEqual(text,self.candidate(text)['text'])

    def test_unrelated_exact_terms_are_not_displaced(self):
        text='cardiovascular risk with blood pressure control'
        self.assertEqual(text,self.candidate(text)['text'])

    def test_previous_by_fix_preserves_negation_and_measurements(self):
        text='No primary allosteronism by this test; keep ≥5 mg.'
        expected='No primary aldosteronism by this test; keep ≥5 mg.'
        self.assertEqual(expected,self.candidate(text)['text'])

    def test_boundaries_and_internal_words_are_protected(self):
        for text in ['tag_elvated blood pressure','tag_pharmacologic therapy','nonelevated blood pressure',
                     'diastolic by blood pressure','cardiovascular not risk','urinary 5 aldosterone']:
            with self.subTest(text=text):self.assertEqual(text,self.candidate(text)['text'])

    def test_two_disjoint_repairs_keep_original_offsets_and_raw_text(self):
        text='elvated blood pressure by urinary allosterone'
        result=self.candidate(text)
        self.assertEqual('elevated blood pressure by urinary aldosterone',result['text'])
        self.assertEqual(text,result['controlled_text'])
        self.assertEqual(2,len(result['changes']))
        for c in result['changes']:self.assertEqual(c['source'],text[c['start']:c['end']])


if __name__=='__main__':unittest.main(verbosity=2)
