"""Run the frozen 30-question development list through SEC-RAG and three baselines.

DeepSeek calls incur cost. Run this explicitly; each result is saved immediately.
Rerunning skips completed cases. No evaluation model is invoked here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sec_rag.experiments.llm_only import run_llm_only
from sec_rag.experiments.prompt_constrained_rag import run_prompt_constrained_rag
from sec_rag.experiments.traditional_rag import run_traditional_rag
from sec_rag.method.runner import run_question
from sec_rag.method.v5 import VERSION, write_json

SPLIT_DIR = ROOT / "storage" / "datasets" / "processed" / "cmedqa2" / "splits" / "v1"
OUTPUT_DIR = ROOT / "storage" / "experiments" / "development" / "cmedqa2" / "first_batch_v1"
METHODS = ("sec_rag", "llm_only", "traditional_rag", "prompt_constrained_rag")
TOP_N = 5


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=30, help="Run first N frozen questions (1..30)")
    parser.add_argument("--check-only", action="store_true", help="Validate the frozen input without API calls")
    parser.add_argument("--split-dir", type=Path, default=SPLIT_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    split_dir = args.split_dir.resolve()
    output_dir = args.output_dir.resolve()
    selected = split_dir / "development_first_batch.csv"
    split_manifest = read(split_dir / "manifest.json")
    if sha(selected) != split_manifest["files"]["development_first_batch"]["sha256"]:
        raise ValueError("Development selection changed after split freeze")
    pool = Path(split_manifest["source_pool"]["path"])
    if sha(pool) != split_manifest["source_pool"]["sha256"]:
        raise ValueError("Question pool changed after split freeze")
    with selected.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not 1 <= args.limit <= len(rows):
        raise ValueError(f"--limit must be 1..{len(rows)}")
    if args.check_only:
        print(json.dumps({"selection_valid": True, "question_count": len(rows), "requested_limit": args.limit, "output_dir": str(output_dir)}, ensure_ascii=False))
        return 0
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "run_manifest.json"
    expected = {"method_version": VERSION, "top_n": TOP_N, "selection_sha256": sha(selected), "selection_path": str(selected)}
    if manifest_path.exists():
        if any(read(manifest_path).get(key) != value for key, value in expected.items()):
            raise ValueError("Frozen input, method version, or retrieval depth changed; use a new run version")
    else:
        write_json(manifest_path, {**expected, "purpose": "First development batch, no validation/test questions", "methods": METHODS})
    status = []
    for row in rows[:args.limit]:
        qid, question, disease = row["qid"], row["question"], row["disease_scope"]
        qdir = output_dir / "questions" / qid
        for method in METHODS:
            output = qdir / "06_final_answer.json" if method == "sec_rag" else qdir / "baselines" / f"{method}.json"
            if output.exists():
                saved = read(output)
                if (method == "sec_rag" and saved.get("status") == "completed" and saved.get("input", {}).get("question") == question) or (method != "sec_rag" and saved.get("status") == "completed" and saved.get("record", {}).get("question") == question):
                    status.append({"qid": qid, "method": method, "status": "resumed"})
                    continue
            try:
                if method == "sec_rag":
                    run_question(question=question, question_id=qid, source_dataset=row["source_dataset"], disease_scope=disease, top_n=TOP_N, output_dir=qdir)
                else:
                    if method == "llm_only":
                        record = run_llm_only(question)
                    else:
                        retrieval = read(qdir / "01_retrieval.json")["retrieval_results"]
                        fn = run_traditional_rag if method == "traditional_rag" else run_prompt_constrained_rag
                        record = fn(question, top_k=TOP_N, disease=disease, retrieval=retrieval)
                    write_json(output, {"status": "completed", "qid": qid, "method": method, "source_retrieval": "01_retrieval.json" if method != "llm_only" else None, "record": record})
                result = {"qid": qid, "method": method, "status": "completed"}
            except Exception as exc:
                result = {"qid": qid, "method": method, "status": "failed", "error": {"type": type(exc).__name__, "message": str(exc)}}
                if method != "sec_rag":
                    write_json(output, {**result, "record": getattr(exc, "record", None)})
            status.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
        write_json(output_dir / "progress.json", {"requested_questions": args.limit, "completed_calls": sum(x["status"] in ("completed", "resumed") for x in status), "failed_calls": sum(x["status"] == "failed" for x in status), "results": status})
    return 1 if any(x["status"] == "failed" for x in status) else 0


if __name__ == "__main__":
    raise SystemExit(main())
