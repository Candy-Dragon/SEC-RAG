from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.method.v5 import (  # noqa: E402
    find_contiguous,
    validate_information_needs,
    validate_evidence_mapping,
    validate_candidate,
    validate_coverage,
    validate_grouping,
    render_candidate_answer,
    insufficient_coverage,
)
from sec_rag.method.runner import completed_stage  # noqa: E402
from sec_rag.method.v5 import VERSION, sha  # noqa: E402
from sec_rag.method.v5 import stage01_retrieval  # noqa: E402


class EvidenceUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.chunk = {
            "chunk_id": "chunk-1",
            "sentences": [
                {"sentence_id": "C1S1", "text": "第一句。"},
                {"sentence_id": "C1S2", "text": "第二句。"},
                {"sentence_id": "C1S3", "text": "第三句。"},
            ],
        }

    def test_accepts_exact_sentence_assignment(self) -> None:
        value = {
            "chunk_id": "chunk-1",
            "evidence_groups": [{"sentence_ids": ["C1S1", "C1S2"]}],
            "excluded_sentences": [{"sentence_id": "C1S3", "reason": "测试排除"}],
        }
        result = validate_grouping(value, [self.chunk])
        self.assertEqual(result["evidence_groups"][0]["sentence_ids"], ["C1S1", "C1S2"])

    def test_rejects_non_contiguous_group(self) -> None:
        value = {
            "chunk_id": "chunk-1",
            "evidence_groups": [{"sentence_ids": ["C1S1", "C1S3"]}],
            "excluded_sentences": [{"sentence_id": "C1S2", "reason": "测试排除"}],
        }
        with self.assertRaises(ValueError):
            validate_grouping(value, [self.chunk])


class ScreeningValidationTests(unittest.TestCase):
    def test_contiguous_quote_ignores_whitespace_only(self) -> None:
        source = "患者出现严重头痛意识障碍神经症状时应立即前往医院接受评估。"
        quote = "患者出现严重头痛意识障碍神经症状时应立即前往医院接受评估。"
        self.assertEqual(find_contiguous("前文。" + source + "后文。", quote), source)

    def test_information_need_must_use_verbatim_source_span(self) -> None:
        value = {
            "original_question": "头痛两天了怎么办？",
            "information_needs": [{"need_id": "Q1", "source_span": "如何治疗", "description": "询问处理方法"}],
            "context_spans": ["头痛两天了"],
        }
        with self.assertRaises(ValueError):
            validate_information_needs(value, "头痛两天了怎么办？")

    def test_unmatched_evidence_cannot_claim_supported_content(self) -> None:
        value = {"evidence_id": "E001", "matched_need_ids": [], "supported_content": ["治疗方法"],
                 "required_conditions": [], "unsupported_extensions": [], "reason": "不匹配"}
        with self.assertRaises(ValueError):
            validate_evidence_mapping(value, "E001", {"Q1"})


class CoverageAndGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.allowed = {"E001"}
        self.coverage = validate_coverage(
            {
                "coverage_items": [
                    {
                        "need_id": "Q1",
                        "source_span": "是否需要就医",
                        "coverage": "full",
                        "evidence_usage": [{"evidence_id": "E001", "supported_content": "就医条件", "required_conditions": [], "used_for_generation": True, "reason": "直接覆盖"}],
                        "supported_scope": ["说明就医条件"], "missing_scope": [], "required_conditions": [], "forbidden_content": ["个体诊断"],
                        "reason": "直接覆盖",
                    }
                ]
            },
            [{"need_id": "Q1", "source_span": "是否需要就医", "description": "询问是否就医"}],
            {"Q1": self.allowed},
        )

    def test_coverage_derives_sufficient(self) -> None:
        self.assertEqual(self.coverage["overall_coverage"], "full")

    def test_partial_coverage_must_be_answered_and_marked_insufficient(self) -> None:
        value = {
            "coverage_items": [{
                "need_id": "Q1",
                "source_span": "如何治疗",
                "coverage": "partial",
                "evidence_usage": [{"evidence_id": "E001", "supported_content": "一般原则", "required_conditions": [], "used_for_generation": True, "reason": "部分支持"}],
                "supported_scope": ["一般原则"], "missing_scope": ["个体方案"], "required_conditions": ["个体治疗条件"], "forbidden_content": ["具体个体治疗方案"],
                "reason": "仅覆盖一般原则",
            }]
        }
        result = validate_coverage(value, [{"need_id": "Q1", "source_span": "如何治疗", "description": "治疗"}], {"Q1": self.allowed})
        self.assertEqual(result["overall_coverage"], "partial")

    def test_no_evidence_coverage_preserves_original_question(self) -> None:
        result = insufficient_coverage("none survived", [{"need_id": "Q1", "source_span": "怎么治疗", "description": "治疗"}])
        self.assertEqual(
            result["coverage_items"][0]["source_span"],
            "怎么治疗",
        )

    def test_rejects_unknown_evidence(self) -> None:
        value = {
            "answer": "回答[E999]",
            "claims": [
                {"claim_id": "C1", "text": "回答", "evidence_ids": ["E999"], "claim_type": "fact"}
            ],
            "insufficient_information": [],
        }
        with self.assertRaises(ValueError):
            validate_candidate(value, self.allowed, set())

    def test_discards_unstructured_answer_free_text(self) -> None:
        value = {
            "answer": "指南支持该结论 [E001]\n\n额外的未验证医学内容。",
            "claims": [
                {"claim_id": "C1", "text": "指南支持该结论", "evidence_ids": ["E001"], "claim_type": "fact"}
            ],
            "insufficient_information": [],
        }
        result = validate_candidate(value, self.allowed, set())
        self.assertNotIn("额外的未验证医学内容", result["answer"])
        self.assertFalse(result["model_answer_matched_structured_sentences"])

    def test_accepts_deterministically_rendered_answer(self) -> None:
        claims = [
            {"claim_id": "C1", "text": "指南支持该结论", "evidence_ids": ["E001"], "claim_type": "fact"}
        ]
        insufficient = [{"need_id": "Q2", "statement": "当前证据未覆盖另一项需求。"}]
        value = {
            "answer": render_candidate_answer(claims, insufficient),
            "claims": claims,
            "insufficient_information": insufficient,
        }
        result = validate_candidate(value, self.allowed, {"Q2"})
        self.assertEqual(result["answer"], value["answer"])

class ResumeValidationTests(unittest.TestCase):
    def test_rejects_cached_stage_after_upstream_change(self) -> None:
        expected_input = {
            "question_id": "TEST_001",
            "source_dataset": "test",
            "question": "测试问题",
            "disease_scope": "hypertension",
            "top_n": 5,
        }
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            folder = Path(temporary)
            source = folder / "01_retrieval.json"
            source.write_text('{"version": 1}', encoding="utf-8")
            stage = folder / "02_evidence_units.json"
            stage.write_text(json.dumps({
                "method_version": VERSION,
                "stage": "02_evidence_units",
                "status": "completed",
                "input": expected_input,
                "source_record": {
                    "path": source.relative_to(ROOT).as_posix(),
                    "sha256": sha(source),
                },
            }), encoding="utf-8")
            self.assertTrue(completed_stage(stage, "02_evidence_units", expected_input, source))
            source.write_text('{"version": 2}', encoding="utf-8")
            self.assertFalse(completed_stage(stage, "02_evidence_units", expected_input, source))


class RetrievalScopeTests(unittest.TestCase):
    def test_rejects_disease_outside_controlled_scope_before_search(self) -> None:
        with self.assertRaises(ValueError):
            stage01_retrieval(
                "测试问题",
                question_id="TEST_SCOPE",
                source_dataset="test",
                disease_scope="unknown_disease",
                top_n=5,
                output_path=ROOT / "unused-test-output.json",
            )


if __name__ == "__main__":
    unittest.main()
