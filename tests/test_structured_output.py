"""Citation normalization must preserve evidence identity and reject guesses."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sec_rag.experiments.structured_output import parse_common_output
from sec_rag.llm.deepseek_client import DeepSeekAPIError


class CitationParsingTests(unittest.TestCase):
    def parse(self, citations):
        return parse_common_output(json.dumps({
            "answer": "Example", "citations": citations,
            "evidence_sufficient": False, "insufficiency_reason": "Conflicting evidence",
        }), evidence_count=5, expected_sufficiency="boolean")

    def test_equivalent_representations_preserve_identity(self):
        parsed, _ = self.parse([1, "2", "证据3", "[证据4]", "5"])
        self.assertEqual(parsed["citations"], [1, 2, 3, 4, 5])

    def test_invalid_or_out_of_range_references_remain_errors(self):
        for value in (True, 1.0, "1.0", "01", " 1", "1,2", "E1", "0", "6", -1):
            with self.subTest(value=value), self.assertRaises(DeepSeekAPIError):
                self.parse([value])
