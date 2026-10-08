import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sec_rag.evaluation.four_methods import split_answer, validate_classification, classify_answer


class UnitTests(unittest.TestCase):
    def test_classifier_receives_one_unit_and_preserves_order(self):
        class Judge:
            def call_json(self,prompt,payload,validator,**kwargs):
                self_test.assertEqual(len(payload['units']),1)
                self_test.assertEqual(payload['units'][0]['id'],'C1')
                text=payload['units'][0]['text']
                kind='evidence_boundary' if text=='证据不足。' else 'medical'
                return {'parsed':validator({'kinds':[kind]})}
        self_test=self
        result=classify_answer(Judge(),'证据不足。需要复查。[证据1]',workers=2)
        self.assertEqual(result['parsed']['kinds'],['evidence_boundary','medical'])
        self.assertFalse(result['parsed']['refusal'])
        self.assertEqual(result['parsed']['claims'][1]['id'],'C2')
        self.assertEqual(result['parsed']['claims'][1]['citations'],['证据1'])

    def test_classification_failure_preserves_other_unit_traces(self):
        from sec_rag.evaluation.ollama_client import LocalJudgeError
        class Judge:
            def call_json(self,prompt,payload,validator,**kwargs):
                if payload['units'][0]['text']=='失败。':raise ValueError('test failure')
                return {'parsed':validator({'kinds':['medical']})}
        with self.assertRaises(LocalJudgeError) as caught:
            classify_answer(Judge(),'复查。失败。',workers=2)
        self.assertEqual([r['status'] for r in caught.exception.trace['unit_traces']],['completed','failed'])

    def test_suffix_citation_stays_with_sentence(self):
        units=split_answer('建议限盐。 [E028][E029]\n证据不足。')
        self.assertEqual(len(units),2)
        self.assertEqual(units[0]['citations'],['E028','E029'])
        self.assertEqual(units[1]['citations'],[])

    def test_contrastive_evidence_gap_preserves_both_clauses(self):
        answer='指南建议手术[证据1]，但未明确术后是否需要化疗。'
        units=split_answer(answer)
        self.assertEqual(len(units),2)
        self.assertEqual(units[0]['citations'],['证据1'])
        self.assertEqual(units[1]['citations'],[])
        self.assertTrue(units[1]['text'].startswith('但未明确'))
        self.assertEqual(''.join(u['text'] for u in units),answer)

    def test_numeric_values_and_quotes_not_rewritten(self):
        answer='“7.8”不能确定。血糖≥5.1 mmol/L且<7.0 mmol/L[证据1]。'
        units=split_answer(answer)
        for u in units:self.assertEqual(answer[u['start']:u['end']],u['text'])
        self.assertIn('≥5.1',units[1]['text'])

    def test_bare_answer_cannot_acquire_citations(self):
        units=split_answer('生活方式干预。复查。')
        parsed=validate_classification({'kinds':['medical','medical'],'refusal':False},units)
        self.assertTrue(all(not c['citations'] for c in parsed['claims']))

    def test_refusal_has_boundary_unit(self):
        units=split_answer('当前指南没有足够证据，无法提供结论。')
        v=validate_classification({'kinds':['evidence_boundary']},units)
        self.assertTrue(v['full_refusal_due_to_evidence'])
        self.assertEqual(len(v['claims']),1)

    def test_partial_answer_is_not_full_refusal(self):
        units=split_answer('应限盐。没有更多指南证据。')
        v=validate_classification({'kinds':['medical','evidence_boundary']},units)
        self.assertFalse(v['full_refusal_due_to_evidence'])

    def test_generic_boundary_is_not_evidence_refusal(self):
        v=validate_classification({'kinds':['boundary']},split_answer('请咨询医生。'))
        self.assertFalse(v['full_refusal_due_to_evidence'])

    def test_missing_classification_fails(self):
        with self.assertRaises(ValueError):
            validate_classification({'kinds':[],'refusal':True},split_answer('证据不足。'))

    def test_cache_revalidation_preserves_original(self):
        units=split_answer('建议限盐。[证据1]')
        v=validate_classification({'kinds':['medical'],'refusal':False},units)
        self.assertEqual(v,validate_classification(v,units))
