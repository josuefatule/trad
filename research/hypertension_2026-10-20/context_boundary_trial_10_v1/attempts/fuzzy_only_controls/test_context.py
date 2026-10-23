import unittest
import evaluate_context as exp


class ContextGuardTests(unittest.TestCase):
    def setUp(self):
        self.item={"concept_id":"x","canonical_en":"primary aldosteronism"}
        self.thresholds={"x":.94}

    def test_shorter_candidate_preserves_by(self):
        text="primary allosteronism by this test"
        old=exp.candidate(text,[self.item],self.thresholds,"individualized")
        new=exp.candidate(text,[self.item],self.thresholds)
        self.assertEqual("primary aldosteronism this test",old["text"])
        self.assertEqual("primary aldosteronism by this test",new["text"])
        self.assertEqual(text,new["controlled_text"])

    def test_veto_after_selection_cannot_find_the_shorter_candidate(self):
        text="primary allosteronism by this test"
        veto=exp.candidate(text,[self.item],self.thresholds,"postselection_veto")
        self.assertEqual(text,veto["text"])

    def test_lexical_neighbor_is_not_mistaken_for_a_spelling_fragment(self):
        text="primary allosteronism patients arrived"
        self.assertEqual("primary aldosteronism patients arrived",exp.candidate(text,[self.item],self.thresholds)["text"])
        self.assertIsNone(exp.token_alignment(("primary","allosteronism","patients"),("primary","aldosteronism")))

    def test_genuine_split_word_remains_recoverable(self):
        text="primary aldous gerinism"
        self.assertEqual("primary aldosteronism",exp.candidate(text,[self.item],self.thresholds)["text"])
        self.assertIsNotNone(exp.token_alignment(("primary","aldous","gerinism"),("primary","aldosteronism")))

    def test_outer_negation_and_quantity_remain_verbatim(self):
        text="No primary allosteronism by this test; keep ≥5 mg."
        output=exp.candidate(text,[self.item],self.thresholds)["text"]
        self.assertEqual("No primary aldosteronism by this test; keep ≥5 mg.",output)

    def test_inner_negation_function_word_and_quantity_rejected(self):
        for text in ["primary not aldosteronism","primary by aldosteronism","primary 5 aldosteronism"]:
            self.assertFalse(exp.guard_span(text,0,len(text),"primary aldosteronism")["accepted"])

    def test_recognized_opposed_qualifiers_are_preserved(self):
        for source,target in [("secondary aldosteronism","primary aldosteronism"),
                              ("diastolic blood pressure","systolic blood pressure"),
                              ("cardiovascular event","cardiovascular events"),
                              ("mineralocorticoid receptors","mineralocorticoid receptor")]:
            self.assertFalse(exp.guard_span(source,0,len(source),target)["accepted"])

    def test_morphological_negation_is_not_corrected_away(self):
        text="nonprimary aldosteronism"
        self.assertIn("morphological_negation_changed",exp.guard_span(text,0,len(text),"primary aldosteronism")["reasons"])

    def test_identifier_boundaries_are_respected(self):
        text="tag_primary allosteronism"
        verdict=exp.guard_span(text,4,len(text),"primary aldosteronism")
        self.assertIn("whole_word_or_identifier_boundary",verdict["reasons"])
        self.assertEqual(text,exp.candidate(text,[self.item],self.thresholds)["text"])

    def test_function_of_remains_in_proper_name(self):
        text="National Instituzes of Health"
        item={"concept_id":"x","canonical_en":"National Institutes of Health"}
        self.assertEqual("National Institutes of Health",exp.candidate(text,[item],{"x":.96})["text"])

    def test_frozen_ten_ids_and_thresholds_are_identical(self):
        terms=exp.prior.load(exp.PRIOR/"selection.json")["selected"]
        results=exp.prior.load(exp.HERE/"term_results.json")
        self.assertEqual([r["concept_id"] for r in terms],[r["concept_id"] for r in results])
        old={r["concept_id"]:r["selected_auto_threshold"] for r in exp.prior.load(exp.PRIOR/"threshold_decisions.json")}
        self.assertEqual(old,{r["concept_id"]:r["unchanged_auto_threshold"] for r in results})

    def test_no_function_word_changes_in_guarded_corpus(self):
        data=exp.prior.load(exp.HERE/"speech_comparison.json")
        self.assertTrue(all(not r["function_word_sequence_changed"] and not r["cue_signature_changed"]
                            for r in data["rows"] if r["profile"]=="preselection_guards"))


if __name__=="__main__":
    unittest.main(verbosity=2)
