"""Offline contract and six-stage integration checks; no clinical quality claims."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sec_rag.method.components import resolve_components, validate_record, validate_links
from sec_rag.pipeline import run


class ComponentTests(unittest.TestCase):
    def test_invalid_selection_fails_before_model_calls(self):
        with self.assertRaises(ValueError):
            resolve_components({"07_verify": "bad:entry"})
        with self.assertRaises(TypeError):
            resolve_components({"02_evidence_units": "sec_rag.utils.stage_runtime:now"})

    def test_changed_question_and_missing_fields_rejected(self):
        with self.assertRaises(ValueError):
            validate_record({"stage": "02_evidence_units", "status": "completed", "input": {}}, "02_evidence_units", {"question": "original"})
        with self.assertRaises(ValueError):
            validate_record({"stage": "02_evidence_units", "status": "completed", "input": {}}, "02_evidence_units", {})

    def test_generation_cannot_cite_outside_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "05.json"
            coverage = {"generation_boundaries": {"allowed_evidence_ids": ["E1"]}}
            source.write_text(json.dumps({"coverage_analysis": coverage}), encoding="utf-8")
            record = {"coverage_analysis": coverage, "approved_evidence": [{"evidence_id": "E1"}],
                      "final_answer": {"claims": [{"evidence_ids": ["E2"]}]}}
            with self.assertRaisesRegex(ValueError, "citations"):
                validate_links(record, "06_final_answer", source)

    def test_structure_cannot_drop_retrieved_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "01.json"
            source.write_text(json.dumps({"retrieval_results": [{"chunk_id": "chunk1"}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "chunk IDs"):
                validate_links({"candidate_chunks": [], "evidence_units": []}, "02_evidence_units", source)

    def test_replacement_runs_all_six_stages_and_preserves_shared_retrieval(self):
        cfg = json.loads((ROOT / "examples/experiment_a.json").read_text(encoding="utf-8"))
        cfg["methods"] = ["sec_rag", "extractive_demo"]
        cfg["components"] = {"02_evidence_units": "sec_rag.structurer.sentences:stage02_sentences"}
        parent = ROOT / "storage/experiments"
        parent.mkdir(parents=True, exist_ok=True)

        def fake_model(stage, filename, data, validate, **kwargs):
            if stage == "03_integrity":
                value = {"evidence_id": data["evidence_id"], "label": "complete", "reason": "synthetic test"}
            elif stage == "04_information_needs":
                q = data["original_question"]
                value = {"original_question": q, "information_needs": [{"need_id": "Q1", "source_span": q, "description": q}], "context_spans": []}
            else:
                value = {"evidence_id": data["evidence"]["evidence_id"], "matched_need_ids": [], "supported_content": [], "required_conditions": [], "unsupported_extensions": [], "reason": "synthetic no coverage"}
            return {"parsed_output": validate(value)}

        with tempfile.TemporaryDirectory(dir=parent) as directory:
            cfg["output_dir"] = Path(directory).relative_to(ROOT).as_posix()
            with patch("sec_rag.filter.integrity.call_json", side_effect=fake_model), patch("sec_rag.filter.applicability.call_json", side_effect=fake_model):
                result = run(cfg)
            self.assertEqual(result["failed"], 0)
            qdir = Path(directory) / "questions/DEMO_001"
            manifest = json.loads((qdir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["stages"]), 6)
            self.assertEqual(manifest["components"]["02_evidence_units"]["target"], cfg["components"]["02_evidence_units"])
            answer = json.loads((qdir / "06_final_answer.json").read_text(encoding="utf-8"))
            self.assertTrue(answer["final_answer"]["answer"])
            self.assertEqual(answer["coverage_analysis"]["overall_coverage"], "none")
            self.assertEqual(run(cfg)["completed"], 2)
            cfg["components"] = {}
            with self.assertRaisesRegex(ValueError, "changed"):
                run(cfg)
