import sys
import unittest
import tempfile
import json
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sec_rag.evaluation.four_methods import evaluate, validate_statements, METRICS, check_inputs


class Judge:
    def __init__(self): self.calls=[]
    def call_json(self,prompt,payload,validator,**kwargs):
        self.calls.append(prompt.name)
        if prompt.name=='00_classify_units.txt':
            value={'kinds':['evidence_boundary' if '证据不足' in payload['units'][0]['text'] else 'medical']}
        elif prompt.name=='01_extract_statements.txt':
            assert set(payload)=={'sentences'}
            assert len(payload['sentences'])==1
            quote=payload['sentences'][0]['text']
            value={'statements':[{'id':'S1','source_sentence_id':'C1','source_quote':quote,'text':'应限盐'},
                                 {'id':'S2','source_sentence_id':'C1','source_quote':quote,'text':'应运动'}]}
        elif prompt.name=='01_claim_entailment.txt':
            value={'judgments':[{'id':'S1','label':True,'reason':'supported'},
                                {'id':'S2','label':False,'reason':'absent'}]}
        elif prompt.name=='02_citation_sentence_support.txt':
            value={'supported':False,'reason':'only one fact supported'}
        else: raise AssertionError('Unexpected evaluation call '+prompt.name)
        return {'parsed':validator(value)}


class ScopeTests(unittest.TestCase):
    def test_actual_prompt_files_exist(self):
        from sec_rag.evaluation.common import check_prompts, PROMPTS
        self.assertEqual(PROMPTS.name, "evaluation")
        check_prompts()

    def test_preflight_checks_prompts_before_any_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("sec_rag.evaluation.common.PROMPTS", Path(directory)):
                with self.assertRaisesRegex(ValueError, "prompt missing"):
                    check_inputs(Path(directory), [], [])

    def test_preflight_rejects_mismatched_question(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); q=root/'questions'/'Q1'; (q/'baselines').mkdir(parents=True)
            (q/'01_retrieval.json').write_text(json.dumps({'input':{'question':'original'},'retrieval_results':[{'chunk_id':'X','text':'evidence'}]}))
            answer=q/'baselines'/'llm_only.json'
            answer.write_text(json.dumps({'status':'completed','record':{'question':'different','answer':'answer'}}))
            with self.assertRaises(ValueError):check_inputs(root,['Q1'],['llm_only'])
            answer.write_text(json.dumps({'status':'completed','record':{'question':'original','answer':'answer'}}))
            first=check_inputs(root,['Q1'],['llm_only'])
            answer.write_text(json.dumps({'status':'completed','record':{'question':'original','answer':'changed'}}))
            self.assertNotEqual(first,check_inputs(root,['Q1'],['llm_only']))

    def run_answer(self,answer,method='sec_rag',evidence=None):
        judge=Judge()
        result=evaluate(judge,'怎么办',answer,[{'chunk_id':'X','text':'应限盐'}],evidence or {},method)
        self.assertEqual(result['status'],'completed',result)
        return result,judge

    def test_statements_and_sentences_have_different_denominators(self):
        r,j=self.run_answer('应限盐并运动。[E1]',evidence={'E1':'应限盐'})
        self.assertEqual(r['result']['guideline_faithfulness'],.5)
        self.assertEqual(r['result']['faithfulness_total'],2)
        self.assertEqual(r['result']['citation_total_sentences'],1)
        self.assertEqual(r['result']['citation_recall'],0)
        self.assertEqual(set(METRICS),{'guideline_faithfulness','citation_recall'})

    def test_broken_citation_is_zero_not_failed(self):
        r,j=self.run_answer('应限盐并运动。[E999]')
        self.assertEqual(r['result']['citation_recall'],0)
        self.assertNotIn('02_citation_sentence_support.txt',j.calls)

    def test_refusal_is_not_perfect_score(self):
        r,j=self.run_answer('证据不足。')
        self.assertIsNone(r['result']['guideline_faithfulness'])
        self.assertIsNone(r['result']['citation_recall'])
        self.assertTrue(r['result']['full_refusal_due_to_evidence'])
        self.assertEqual(len(j.calls),1)

    def test_bare_model_has_no_citation_score(self):
        r,j=self.run_answer('应限盐并运动。',method='llm_only')
        self.assertIsNone(r['result']['citation_recall'])
        self.assertEqual(r['result']['guideline_faithfulness'],.5)

    def test_missing_sentence_in_extraction_rejected(self):
        with self.assertRaises(ValueError):
            validate_statements({'statements':[{'id':'S1','source_sentence_id':'C1','text':'x'}]},[{'id':'C1','text':'a'},{'id':'C2','text':'b'}])

    def test_excluded_sentence_is_not_sent_to_extractor(self):
        self.run_answer('应限盐并运动。[E1]证据不足。', evidence={'E1':'应限盐'})

    def test_quote_from_another_sentence_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'source_quote'):
            validate_statements({'statements':[{'id':'S1','source_sentence_id':'C1',
                'source_quote':'证据不足','text':'证据不足'}]}, [{'id':'C1','text':'应限盐。'}])
