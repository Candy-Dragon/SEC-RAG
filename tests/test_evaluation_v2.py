import sys
import unittest
import tempfile
from unittest.mock import patch, Mock
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sec_rag.evaluation.four_methods import summarize, METRICS
from sec_rag.evaluation.ollama_client import OllamaJudge

class FairEvaluationTests(unittest.TestCase):
    def test_cache_reuses_identical_input_and_invalidates_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            prompt=root/'prompt.txt';prompt.write_text('first',encoding='utf-8')
            judge=OllamaJudge(cache_dir=root/'cache');judge.model_digest='test-digest'
            response=Mock()
            response.json.return_value={'message':{'content':'{"ok":true}'},'done_reason':'stop'}
            with patch('sec_rag.evaluation.ollama_client.httpx.post',return_value=response) as post:
                judge.call_json(prompt,{'answer':'one'},lambda v:v)
                self.assertTrue(judge.call_json(prompt,{'answer':'one'},lambda v:v)['cache_hit'])
                self.assertEqual(post.call_count,1)
                self.assertIs(post.call_args.kwargs['trust_env'], False)
                prompt.write_text('changed',encoding='utf-8')
                judge.call_json(prompt,{'answer':'one'},lambda v:v)
                self.assertEqual(post.call_count,2)

    def test_failures_do_not_become_refusals_or_zero_scores(self):
        result={m:None for m in METRICS}
        result.update(information_need_completeness=0.0,has_medical_content=False,full_refusal_due_to_evidence=True)
        table=summarize([{"method":"sec_rag","status":"completed","result":result},{"method":"sec_rag","status":"failed"}])[0]
        self.assertEqual(table["failed"],1)
        self.assertEqual(table["behavior_rate_denominator"],1)
        self.assertEqual(table["evidence_refusal_rate"],1)
        self.assertEqual(table["guideline_faithfulness"],"N/A")
        self.assertNotIn("information_need_completeness",table)
