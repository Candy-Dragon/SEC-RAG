"""Experiment Step 02: run one Traditional RAG question.

INPUT:
  One question, optional disease key, and Top-k.

OUTPUT:
  Console evidence/answer and
  storage/experiments/testing/single_question/common_output_v1/traditional_rag/<run_id>.json

RUN:
  python scripts/experiments/02_run_traditional_rag.py \
    "高血压的诊断标准是什么？" --disease hypertension --top-k 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.experiments.run_record import write_run_record  # noqa: E402
from sec_rag.experiments.traditional_rag import run_traditional_rag  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Traditional RAG baseline")
    parser.add_argument("question", help="Chinese medical question")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--disease", help="optional disease folder key")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    record = run_traditional_rag(
        args.question, top_k=args.top_k, disease=args.disease
    )
    output_path = write_run_record(record)
    print("Experiment - 02 Traditional RAG")
    print("=" * 44)
    print(f"Question: {record['question']}")
    print(f"Retrieved: {len(record['retrieval'])} chunks")
    for evidence in record["retrieval"]:
        print(
            f"  [{evidence['rank']}] score={evidence['score']} "
            f"{evidence['source_file']} pages={evidence['page_start']}-{evidence['page_end']}"
        )
    print(f"Answer:\n{record['answer']}")
    print(f"Model:   {record['model']['returned_model']}")
    print(f"Tokens:  {record['model']['usage']['total_tokens']}")
    print(f"Latency: {record['model']['latency_seconds']}s")
    print(f"Saved:   {output_path}")
    print("\nExperiment 02 Traditional RAG: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
