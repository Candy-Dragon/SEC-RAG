"""Experiment Step 01: run one LLM-only baseline question.

INPUT:
  One question provided on the command line.

OUTPUT:
  Console answer and
  storage/experiments/testing/single_question/common_output_v1/llm_only/<run_id>.json

RUN:
  python scripts/experiments/01_run_llm_only.py "高血压的诊断标准是什么？"
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

from sec_rag.experiments.llm_only import run_llm_only  # noqa: E402
from sec_rag.experiments.run_record import write_run_record  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the LLM-only baseline")
    parser.add_argument("question", help="Chinese medical question")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    record = run_llm_only(args.question)
    output_path = write_run_record(record)
    print("Experiment - 01 LLM-only")
    print("=" * 40)
    print(f"Question: {record['question']}")
    print(f"Answer:   {record['answer']}")
    print(f"Model:    {record['model']['returned_model']}")
    print(f"Tokens:   {record['model']['usage']['total_tokens']}")
    print(f"Latency:  {record['model']['latency_seconds']}s")
    print(f"Saved:    {output_path}")
    print("\nExperiment 01 LLM-only: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
