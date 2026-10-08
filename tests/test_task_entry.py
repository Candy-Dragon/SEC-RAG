import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("task_entry", ROOT / "scripts/run.py")
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class TaskEntryTests(unittest.TestCase):
    def test_all_registered_scripts_exist_and_use_current_python(self):
        config = json.loads((ROOT / "configs/tasks.json").read_text(encoding="utf-8"))
        for task in config["tasks"]:
            command = entry.build_command(task, config, [])
            self.assertEqual(command[:2], [sys.executable, "-s"])
            self.assertTrue(Path(command[2]).is_file())

    def test_user_arguments_are_preserved_without_shell_parsing(self):
        config = {"tasks": {"test": {"script": "scripts/sec_rag/01_run_question.py"}}}
        question = "问题含 空格 & 符号"
        self.assertEqual(entry.build_command("test", config, ["--", question])[-1], question)

    def test_task_cannot_escape_script_directory(self):
        config = {"tasks": {"test": {"script": "README.md"}}}
        with self.assertRaises(ValueError):
            entry.build_command("test", config, [])
