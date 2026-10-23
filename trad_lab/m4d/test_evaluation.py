"""Clinical scoring boundaries and exact audio provenance, CPU-only."""
import json
from pathlib import Path
import tempfile
import unittest
import wave
from trad_lab.m4d.analysis import phrase_status, sensitive_changes, freeze_check_regions, complete_group
from trad_lab.m4d.evaluate import read_wav, write_excerpt, ROOT


class EvaluationTests(unittest.TestCase):
    def test_partial_corpus_cannot_be_labelled_complete(self):
        rows=[{'sample':'cardio_01','status':'completed'}]
        self.assertFalse(complete_group(rows,'full'))
        rows.extend([{'sample':'cardio_02','status':'completed'},{'sample':'cardio_03','status':'failed'}])
        self.assertFalse(complete_group(rows,'full'))
        rows[-1]['status']='completed';self.assertTrue(complete_group(rows,'full'))

    def test_treatment_negation_is_not_normalized_away(self):
        self.assertTrue(phrase_status('UNTREATED','untreated stage 2 hypertension')['matched'])
        self.assertFalse(phrase_status('UNTREATED',"I'm treated stage two hypertension")['matched'])
        self.assertTrue(phrase_status('UNTREATED',"I'm treated stage two hypertension")['critical_conflict'])

    def test_range_is_not_single_number_format_equivalence(self):
        self.assertTrue(phrase_status('YEARS','every four to six years')['matched'])
        self.assertTrue(phrase_status('YEARS','every 4 to 6 years')['matched'])
        for text in ('every 46 years','every forty six years'):
            self.assertFalse(phrase_status('YEARS',text)['matched'])
            self.assertTrue(phrase_status('YEARS',text)['critical_conflict'])

    def test_opposed_term_and_numeric_value_remain_distinct(self):
        self.assertTrue(phrase_status('ORTHO','orthostatic hypotension')['matched'])
        self.assertTrue(phrase_status('ORTHO','orthostatic hypertension')['critical_conflict'])
        self.assertTrue(phrase_status('BP140','140 over 19')['critical_conflict'])
        self.assertFalse(phrase_status('BP140','140 over 19')['matched'])

    def test_conflicting_forms_are_not_a_clean_pass(self):
        row=phrase_status('ORTHO','orthostatic hypotension, orthostatic hypertension')
        self.assertEqual(row['status'],'conflicting_forms')
        self.assertTrue(row['critical_conflict'])

    def test_morphology_and_range_revision_generate_alerts_only(self):
        before='untreated stage two hypertension';after="I'm treated stage two hypertension"
        self.assertIn('treatment_or_morphological_polarity',sensitive_changes(before,after))
        self.assertIn('range_to_single_value',sensitive_changes('every four to six years','every 46 years'))
        self.assertEqual(before,'untreated stage two hypertension')
        self.assertEqual(sensitive_changes(before,before),[])

    def test_partial_expression_is_not_whole_sentence_truth(self):
        self.assertEqual(phrase_status('BP140','the classical definition')['status'],'expression_not_matched_review')
        self.assertEqual(phrase_status('BP140','the classical definition')['scope'],
                         'Expression-level review against user provisional adjudication; not whole-clip WER or clinical validation')

    def test_excerpt_preserves_exact_bytes_and_rejects_outside(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'logs/trad_lab',prefix='m4d_test_') as tmp:
            folder=Path(tmp);self.assertTrue(folder.resolve().is_relative_to(ROOT/'logs/trad_lab'))
            raw=bytes(range(256))*100;source=folder/'source.s16le';source.write_bytes(raw)
            target=folder/'clip.wav';write_excerpt(source,123,567,target)
            self.assertEqual(read_wav(target),raw[246:1134])
            with self.assertRaises(ValueError):write_excerpt(source,-1,10,folder/'bad.wav')
            with self.assertRaises(ValueError):write_excerpt(source,0,len(raw),folder/'bad.wav')

    def test_checking_mask_does_not_relabel_same_corpus_independent(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'logs/trad_lab',prefix='m4d_test_') as tmp:
            freeze_check_regions(Path(tmp));d=json.loads((Path(tmp)/'checking_regions.json').read_text())
            self.assertIn('No independent speakers',d['independence'])
            rows={r['id']:r for r in d['samples']}
            self.assertEqual(rows['cardio_02']['checking_words'],1781)
            self.assertEqual(rows['cardio_02']['excluded_selection_token_indices'],[])
            self.assertGreater(rows['cardio_01']['checking_words'],0)
            self.assertLess(rows['cardio_03']['checking_words'],rows['cardio_03']['reference_words'])

if __name__=='__main__':unittest.main()
