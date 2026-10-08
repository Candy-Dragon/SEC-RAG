"""Regression checks for evidence units detached from their source scope."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sec_rag.method.v5 import applicability_evidence_input


class SourceContextTests(unittest.TestCase):
    def setUp(self):
        self.unit = {
            "evidence_id": "E002", "source_chunk_id": "c1", "source_file": "guide.pdf",
            "source_pages": [59, 59], "section_heading": "", "sentence_ids": ["S2"],
            "evidence_text": "应合理选择降压药。",
        }
        self.chunks = {"c1": {"sentences": [
            {"sentence_id": "S1", "text": "药物引起血压升高时，可考虑以下处理。"},
            {"sentence_id": "S2", "text": "应合理选择降压药。"},
            {"sentence_id": "S3", "text": "另一疾病章节。"},
        ]}}

    def test_previous_scope_reaches_model_without_expanding_approved_quote(self):
        payload = applicability_evidence_input(self.unit, self.chunks)
        self.assertIn("药物引起血压升高", payload["source_chunk_sentences"][0]["text"])
        self.assertEqual(payload["evidence_text"], "应合理选择降压药。")
        self.assertEqual(payload["evidence_sentence_ids"], ["S2"])

    def test_missing_source_cannot_silently_fall_back_to_isolated_quote(self):
        with self.assertRaises(ValueError):
            applicability_evidence_input(self.unit, {})

    def test_source_from_different_sentence_set_is_rejected(self):
        self.chunks["c1"]["sentences"] = [{"sentence_id": "S9", "text": "不相关原文。"}]
        with self.assertRaises(ValueError):
            applicability_evidence_input(self.unit, self.chunks)


if __name__ == "__main__":
    unittest.main()
