from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from sec_rag.evaluation.ollama_client import OllamaJudge
print(json.dumps(OllamaJudge().check(), ensure_ascii=False, indent=2))
