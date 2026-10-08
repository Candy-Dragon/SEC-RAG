"""Run or resume one SEC-RAG v5 question."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.config import settings  # noqa: E402
from sec_rag.method.runner import run_question  # noqa: E402
from sec_rag.method.v5 import VERSION  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--source-dataset", default="manual")
    parser.add_argument("--disease", required=True)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or (
        settings.storage_path / "experiments" / "testing" / "single_question" / VERSION / args.question_id
    )
    manifest = run_question(
        question=args.question,
        question_id=args.question_id,
        source_dataset=args.source_dataset,
        disease_scope=args.disease,
        top_n=args.top_n,
        output_dir=output_dir.resolve(),
    )
    final_path = ROOT / manifest["final_record"]["path"]
    final = json.loads(final_path.read_text(encoding="utf-8"))["final_answer"]
    print(final["answer"])
    print(f"Saved: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
