"""Public quick-start contracts: no local datasets or credentials required."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sec_rag.pipeline import run


class PublicEntryTests(unittest.TestCase):
    def test_full_and_replacement_examples_preflight_without_models(self):
        for name in ("experiment_full.json", "experiment_sentence_units.json"):
            cfg = json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))
            result = run(cfg, check_only=True)
            self.assertFalse(result["model_called"])
            self.assertEqual(len(result["methods"]), 4)

    def test_environment_layout_does_not_require_private_data(self):
        spec = importlib.util.spec_from_file_location("env_check", ROOT / "scripts/00_check_env.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.check_project_layout(), [])

    def test_no_default_private_experiment_in_task_catalog(self):
        tasks = json.loads((ROOT / "configs/tasks.json").read_text(encoding="utf-8"))["tasks"]
        self.assertEqual(tasks["experiment"]["args"], [])
        self.assertEqual(tasks["evaluate"]["args"], [])
        self.assertNotIn("generate", tasks)
