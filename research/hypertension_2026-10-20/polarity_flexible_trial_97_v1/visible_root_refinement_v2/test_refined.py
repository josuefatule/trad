import unittest
import pressure_refined as refined
import test_pressure as initial
import run_flexible as exp


class RefinedPressureTests(initial.PressureDirectionTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        original=exp.candidate
        def result(text,profile):
            if not profile.startswith('direction_guard'):return original(text,profile)
            return refined.candidate(text,cls.selected,cls.profiles[profile],cls.variants)
        exp.candidate=result

    def test_visible_root_suffix_typos_recover_without_crossing_direction(self):
        for text in ['resistant hypertesion','resistant hypertesnion','resistant hypertexnsion','resistant hypertezsion']:
            with self.subTest(text=text):
                self.assertEqual(['HYPER'],refined.direction_signature(text)['directions'])
                self.assertEqual('resistant hypertension',exp.candidate(text,'direction_guard_same')['text'])

    def test_ambiguous_missing_direction_still_abstains(self):
        self.assertTrue(refined.direction_signature('hypetension')['ambiguous'])
        self.assertEqual('primary hypetension',exp.candidate('primary hypetension','direction_guard_cap088')['text'])

    def test_directional_suffix_typo_cannot_cross_to_opposite_family(self):
        self.assertFalse(refined.direction_verdict('primary hypotesion','primary hypertension')['accepted'])
        self.assertFalse(refined.direction_verdict('primary hypertesion','primary hypotension')['accepted'])


if __name__=='__main__':unittest.main(verbosity=2)
