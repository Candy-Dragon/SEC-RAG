import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sec_rag.data.adapters import load_questions
from sec_rag.pipeline import run, prepare, resolve_method
from sec_rag.config import settings


class PipelineTests(unittest.TestCase):
    def config(self, label):
        return json.loads((ROOT / f"examples/experiment_{label}.json").read_text(encoding="utf-8"))

    def test_two_formats_and_two_knowledge_bases_offline(self):
        parent = ROOT / "storage/experiments"
        parent.mkdir(parents=True, exist_ok=True)
        old_kb = settings.knowledge_base_root
        for label in ("a", "b"):
            with tempfile.TemporaryDirectory(dir=parent) as directory:
                cfg = self.config(label)
                cfg["output_dir"] = Path(directory).relative_to(ROOT).as_posix()
                self.assertFalse(run(cfg, check_only=True)["model_called"])
                result = run(cfg)
                self.assertEqual((result["completed"], result["failed"]), (1, 0))
                qid = "DEMO_001" if label == "a" else "DEMO_002"
                saved = json.loads((Path(directory) / "questions" / qid / "baselines/extractive_demo.json").read_text(encoding="utf-8"))
                self.assertIn(f"文档 {label.upper()}", saved["record"]["answer"])
                self.assertEqual(run(cfg)["completed"], 1)
                cfg["top_n"] = 4
                with self.assertRaisesRegex(ValueError, "changed"):
                    run(cfg)
        self.assertEqual(settings.knowledge_base_root, old_kb)

    def test_dataset_duplicate_and_traversal_ids_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "input.jsonl"
            for ids in (["x", "x"], ["../bad"]):
                p.write_text("\n".join(json.dumps({"id": x, "q": "q", "d": "d"}) for x in ids), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_questions(p, format="jsonl", columns={"qid": "id", "question": "q", "disease_scope": "d"}, dataset="sample")

    def test_scope_and_method_validation(self):
        cfg = self.config("a")
        cfg["top_n"] = 6
        with self.assertRaises(ValueError): prepare(cfg)
        cfg = self.config("a")
        cfg["methods"] = ["unknown"]
        with self.assertRaises(ValueError): prepare(cfg)

    def test_sec_rag_adapter_uses_keyword_contract(self):
        parent = ROOT / "storage/experiments"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            cfg = self.config("a"); cfg["methods"] = ["sec_rag"]
            cfg["output_dir"] = Path(directory).relative_to(ROOT).as_posix()
            from sec_rag.method.runner import run_question
            with patch("sec_rag.method.runner.run_question", autospec=run_question) as method:
                self.assertEqual(run(cfg)["failed"], 1)
                self.assertEqual(method.call_args.kwargs["question_id"], "DEMO_001")

    def test_builtin_cannot_be_replaced_by_plugin(self):
        cfg = self.config("a"); cfg["plugins"]["sec_rag"] = "bad:entry"
        with self.assertRaises(ValueError): prepare(cfg)

    def test_modified_or_missing_artifacts_rejected_before_resume(self):
        parent = ROOT / "storage/experiments"
        for relative in ("01_retrieval.json", "baselines/extractive_demo.json"):
            with tempfile.TemporaryDirectory(dir=parent) as directory:
                cfg = self.config("a")
                cfg["output_dir"] = Path(directory).relative_to(ROOT).as_posix()
                self.assertEqual(run(cfg)["failed"], 0)
                target = Path(directory) / "questions/DEMO_001" / relative
                target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "modified"):
                    run(cfg)
                target.unlink()
                with self.assertRaisesRegex(ValueError, "missing"):
                    run(cfg)
