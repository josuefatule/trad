import json
from pathlib import Path
import tempfile
import unittest

from trad_lab.audio import digest
from trad_lab.m4.references import validated_reference
from trad_lab.m4.report import format_equivalence
from trad_lab.metrics import metrics


class M4ReferenceTests(unittest.TestCase):
    def test_unvalidated_or_changed_fragment_never_receives_accuracy_reference(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'logs') as folder:
            folder=Path(folder);wav=folder/'clip.wav';text=folder/'reference.txt'
            wav.write_bytes(b'fake audio for hash gate');text.write_text('No edema. 5 mg.',encoding='utf-8')
            sample={'id':'s','wav_path':str(wav),'reference_path':str(text)}
            self.assertIsNone(validated_reference(sample,{'accepted':{}}))
            validation={'accepted':{'s':{'wav_sha256':digest(wav),'reference_sha256':digest(text),'temporal_validation':'user_accepted'}}}
            self.assertEqual(validated_reference(sample,validation),'No edema. 5 mg.')
            text.write_text('changed',encoding='utf-8')
            with self.assertRaises(ValueError):validated_reference(sample,validation)


class M4WaveformTests(unittest.TestCase):
    def test_secondary_format_review_never_erases_negation_or_numeric_difference(self):
        a='Stage 1 has no edema and 5% risk.'
        equivalent='Stage one has no edema and 5 percent risk.'
        changed='Stage one has edema and 50 percent risk.'
        self.assertEqual(metrics(format_equivalence(a),format_equivalence(equivalent))['wer'],0)
        result=metrics(format_equivalence(a),format_equivalence(changed))
        self.assertEqual(result['word_errors'],2)
        self.assertTrue(result['risk_flag_counts']['negation_cue'])
        self.assertTrue(result['risk_flag_counts']['number_or_numeric_word'])

    def test_waveform_alignment_preserves_known_delay_under_gain_dc_and_polarity(self):
        try:import numpy as np
        except ImportError:self.skipTest('Run waveform tests with existing ASR venv (numpy/scipy)')
        from trad_lab.m4.audio_analysis import best_match
        rng=np.random.default_rng(1404)
        source=rng.normal(size=10000);template=source[2500:4000]
        captured=np.pad(-2*source+4,(137,200))
        index,correlation=best_match(template,captured)
        self.assertEqual(index,2637)
        self.assertAlmostEqual(correlation,-1.,places=8)


if __name__=='__main__':unittest.main()
