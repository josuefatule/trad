import unittest
import boundary_normalizer as second
import test_controls as first_tests


class RefinedPolicyTests(first_tests.LaboratoryPolicyTests):
    def candidate(self,text,profile='all_fixes'):
        return second.candidate(text,self.selected,self.thresholds,self.variants,profile)

    def test_identifier_prefix_protects_nested_suffixes(self):
        for text in ['tag_target sytolic blood pressure','tag_non-elvated blood pressure',
                     'tag_target SYTOLIC BLOOD PRESSURE','tag_non-elvated blood pressure by this test']:
            with self.subTest(text=text):self.assertEqual(text,self.candidate(text)['text'])

    def test_protected_identifier_does_not_block_disjoint_real_repair(self):
        text='tag_target sytolic blood pressure; urinary allosterone by this test'
        self.assertEqual('tag_target sytolic blood pressure; urinary aldosterone by this test',self.candidate(text)['text'])

    def test_same_phrase_outside_identifier_remains_repairable(self):
        self.assertEqual('target systolic blood pressure by this test',self.candidate('target sytolic blood pressure by this test')['text'])
        self.assertEqual('non-elevated blood pressure',self.candidate('non-elvated blood pressure')['text'])


if __name__=='__main__':unittest.main(verbosity=2)
