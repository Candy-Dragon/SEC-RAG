"""Experiment Step 03: run one Prompt-Constrained RAG question.

OUTPUT:
  storage/experiments/testing/single_question/common_output_v1/prompt_constrained_rag/<run_id>.json

RUN:
  python scripts/experiments/03_run_prompt_constrained_rag.py \
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

from sec_rag.experiments.prompt_constrained_rag import (  # noqa: E402
    run_prompt_constrained_rag,
)
from sec_rag.experiments.run_record import write_run_record  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Prompt-Constrained RAG")
    parser.add_argument("question", help="Chinese medical question")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--disease", help="optional disease folder key")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    record = run_prompt_constrained_rag(
        args.question, top_k=args.top_k, disease=args.disease
    )
    output_path = write_run_record(record)
    output = record["method_output"]
    print("Experiment - 03 Prompt-Constrained RAG")
    print("=" * 51)
    print(f"Question:            {record['question']}")
    print(f"Retrieved:           {len(record['retrieval'])} chunks")
    print(f"Evidence sufficient: {output['evidence_sufficient']}")
    print(f"Citations:           {output['citations']}")
    print(f"Answer:\n{record['answer']}")
    if output["insufficiency_reason"]:
        print(f"Insufficiency reason: {output['insufficiency_reason']}")
    print(f"Model:               {record['model']['returned_model']}")
    print(f"Tokens:              {record['model']['usage']['total_tokens']}")
    print(f"Latency:             {record['model']['latency_seconds']}s")
    print(f"Saved:               {output_path}")
    print("\nExperiment 03 Prompt-Constrained RAG: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
