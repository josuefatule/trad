import unittest
import run_flexible as exp
import pressure_guard as guard


class PressureDirectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        exp.INPUTS=exp.inputs()
        cls.selected,cls.profiles,cls.variants=exp.INPUTS

    def test_known_three_false_rewrites_are_blocked_at_every_cap(self):
        for profile in ['direction_guard_cap092','direction_guard_cap090','direction_guard_cap088']:
            for text in ['They discussed primary hypotension today.','They discussed orthostatic hypertension today.','They discussed secondary hypotension today.']:
                with self.subTest(profile=profile,text=text):self.assertEqual(text,exp.candidate(text,profile)['text'])

    def test_opposite_direction_is_rejected_before_selection_in_both_directions(self):
        for source,target in [('primary hypotension','primary hypertension'),('orthostatic hypertension','orthostatic hypotension')]:
            selected=[dict(concept_id='x',canonical_en=target)]
            r=guard.candidate(source,selected,{'x':.86},[])
            self.assertEqual(source,r['text'])
            self.assertTrue(any('pressure_direction_changed_or_unproven' in b['reasons'] for b in r['blocked']))

    def test_visible_direction_allows_same_direction_spelling_repair(self):
        for text,expected in [('primary hypertenson by this test','primary hypertension by this test'),
                              ('orthostatic hypotenson by this test','orthostatic hypotension by this test')]:
            self.assertEqual(expected,exp.candidate(text,'direction_guard_cap088')['text'])

    def test_split_tokens_keep_direction(self):
        self.assertEqual(['HYPER'],guard.direction_signature('hyper tension')['directions'])
        self.assertEqual(['HYPO'],guard.direction_signature('hypo-tension')['directions'])
        self.assertEqual('primary hypertension by this test',exp.candidate('primary hyper tension by this test','direction_guard_cap088')['text'])

    def test_ambiguous_root_abstains_instead_of_choosing_a_direction(self):
        self.assertTrue(guard.direction_signature('hypetension')['ambiguous'])
        for target in ['primary hypertension','primary hypotension']:
            r=guard.candidate('primary hypetension',[dict(concept_id='x',canonical_en=target)],{'x':.86},[])
            self.assertEqual('primary hypetension',r['text'])

    def test_direction_cannot_disappear_appear_or_change_order(self):
        for source,target in [('hypertension','pressure'),('pressure','hypotension'),
                              ('hypertension and hypotension','hypotension and hypertension')]:
            self.assertFalse(guard.direction_verdict(source,target)['accepted'])

    def test_anti_hypertension_spelling_repair_keeps_same_direction(self):
        self.assertEqual('antihypertensive medication',exp.candidate('antihypertension medication','direction_guard_cap090')['text'])

    def test_blocked_pressure_does_not_block_a_disjoint_repair(self):
        text='primary hypotension; urinary allosterone by this test'
        self.assertEqual('primary hypotension; urinary aldosterone by this test',exp.candidate(text,'direction_guard_cap090')['text'])

    def test_previous_by_negation_and_measurement_guards_remain(self):
        text='No primary allosteronism by this test; keep ≥5 mg.'
        self.assertEqual('No primary aldosteronism by this test; keep ≥5 mg.',exp.candidate(text,'direction_guard_cap090')['text'])

    def test_variants_plural_and_identifiers_remain_protected(self):
        for text in ['pharmacologic therapy','diastolic blood pressures','cardiovascular risks',
                     'tag_target sytolic blood pressure','tag_non-elvated blood pressure']:
            with self.subTest(text=text):self.assertEqual(text,exp.candidate(text,'direction_guard_cap088')['text'])

    def test_caps_only_lower_existing_active_thresholds(self):
        before=self.profiles['previous97']
        self.assertEqual(97,len(before));self.assertEqual(17,sum(v is None for v in before.values()))
        for profile in exp.PROFILES:
            self.assertEqual(set(before),set(self.profiles[profile]))
            for cid,value in self.profiles[profile].items():
                if before[cid] is None:self.assertIsNone(value)
                else:self.assertLessEqual(value,before[cid])


if __name__=='__main__':unittest.main(verbosity=2)
