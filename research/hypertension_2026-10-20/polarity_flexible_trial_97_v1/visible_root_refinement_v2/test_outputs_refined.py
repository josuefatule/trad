import unittest
import pressure_refined as refined
import test_outputs as initial
import run_flexible as exp
from pathlib import Path

FINAL=Path(__file__).resolve().parent
FIRST=FINAL.parent


class RefinedOutputVerification(initial.OutputVerification):
    @classmethod
    def setUpClass(cls):
        exp.HERE=FINAL
        initial.guard=refined
        cls.corpus=exp.load(FINAL/'speech_comparison.json')

    def test_frozen_code_and_inputs_unchanged(self):
        for r in exp.load(FIRST/'protocol.json')['source_hashes']:
            self.assertEqual(r['sha256'],exp.sha(exp.ROOT/r['path']))
        protocol=exp.load(FINAL/'protocol.json')
        for r in protocol['sources']:self.assertEqual(r['sha256'],exp.sha(FINAL/r['name']))
        self.assertEqual(protocol['inputs_sha256'],exp.sha(FINAL/'inputs.json'))

    def test_first_replay_evidence_remains_unchanged(self):
        for r in exp.load(FIRST/'first_replay_manifest.json')['files']:
            self.assertEqual(r['sha256'],exp.sha(FIRST/r['name']))

    def test_reuse_excludes_every_previously_vetoed_pressure_case(self):
        for name in ['pressure','constructed','context','regression']:
            before={(r['profile'],r['case_id']):r for r in exp.load(FIRST/(name+'_comparison.json'))['rows']}
            after=exp.load(FINAL/(name+'_comparison.json'))['rows']
            for row in after:
                previous=before[(row['profile'],row['case_id'])]
                if row['reused_first_revision_output']:
                    if row['profile'].startswith('direction_guard'):self.assertEqual(0,previous['direction_guard_blocks'])
                    self.assertEqual(previous['output'],row['output'])
                elif row['profile'].startswith('direction_guard'):self.assertGreater(previous['direction_guard_blocks'],0)

    def test_speech_reuse_requires_identical_directional_candidate_filter(self):
        before={(r['model'],r['sample_id'],r['profile']):r for r in exp.load(FIRST/'speech_comparison.json')['outputs']}
        for row in self.corpus['outputs']:
            if not row.get('reused_identical_candidate_filter'):continue
            old=before[(row['model'],row['sample_id'],row['profile'])]
            self.assertEqual(old['candidate_text'],row['candidate_text'])
            for b in old['blocked']:
                if 'pressure_direction_changed_or_unproven' in b['reasons']:
                    self.assertFalse(refined.direction_verdict(b['source'],b['canonical'])['accepted'])


if __name__=='__main__':unittest.main(verbosity=2)
