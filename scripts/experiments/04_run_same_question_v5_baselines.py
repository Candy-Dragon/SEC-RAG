"""Run the three retained baselines against a completed SEC-RAG v5 run.

All RAG baselines consume the exact saved stage-01 BM25 results. This script
never calls the old SEC-RAG method and never passes reference answers to a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.experiments.llm_only import run_llm_only  # noqa: E402
from sec_rag.experiments.prompt_constrained_rag import run_prompt_constrained_rag  # noqa: E402
from sec_rag.experiments.run_record import write_run_record  # noqa: E402
from sec_rag.experiments.traditional_rag import run_traditional_rag  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="SEC-RAG v5 question directory")
    parser.add_argument("--output-scope", default="testing/same_question_v5")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    run_manifest = read_json(run_dir / "run_manifest.json")
    if run_manifest.get("method_version") != "sec-rag-v5" or run_manifest.get("status") != "completed":
        raise ValueError("The SEC-RAG v5 run must be completed before baselines run")
    retrieval_path = run_dir / "01_retrieval.json"
    retrieval = read_json(retrieval_path)
    if retrieval.get("stage") != "01_retrieval" or retrieval.get("status") != "completed":
        raise ValueError("Missing completed stage-01 retrieval")
    question = retrieval["input"]["question"]
    disease = retrieval["input"]["disease_scope"]
    chunks = retrieval["retrieval_results"]
    records = {
        "llm_only": run_llm_only(question),
        "traditional_rag": run_traditional_rag(question, top_k=len(chunks), disease=disease, retrieval=chunks),
        "prompt_constrained_rag": run_prompt_constrained_rag(question, top_k=len(chunks), disease=disease, retrieval=chunks),
    }
    saved = {}
    for method, record in records.items():
        record["source_sec_rag_v5_run"] = run_dir.relative_to(ROOT).as_posix()
        record["source_retrieval_sha256"] = sha(retrieval_path)
        saved[method] = write_run_record(record, result_scope=args.output_scope).relative_to(ROOT).as_posix()
    output = {"source_run": run_dir.relative_to(ROOT).as_posix(), "source_retrieval_sha256": sha(retrieval_path), "records": saved}
    summary_path = run_dir / "baselines_summary.json"
    summary_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
