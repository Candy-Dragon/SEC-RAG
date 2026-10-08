"""cMedQA2 Step 3 - Build question pool.

INPUT:
  storage/datasets/processed/cmedqa2/candidates/candidates_all.csv

OUTPUT:
  storage/datasets/processed/cmedqa2/pool/question_pool_all.csv

ACTION:
  Dedupe + assign qid. No extra invented labels.

RUN:
  python scripts/cmedqa2/03_build_question_pool.py
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.data.cmedqa2.question_pool import (  # noqa: E402
    build_question_pool,
    dedupe_rows,
    default_candidates_path,
    read_csv,
    summarize_pool,
    write_question_pool,
)


def main() -> int:
    print("cMedQA2 - 03 build question pool")
    print("=" * 48)

    input_path = default_candidates_path()
    if not input_path.exists():
        print(f"Missing input: {input_path}")
        print("Run: python scripts/cmedqa2/02_build_candidates.py")
        return 1

    raw_rows = read_csv(input_path)
    deduped_rows, removed = dedupe_rows(raw_rows)
    pool_rows = build_question_pool(deduped_rows)
    output_path = write_question_pool(pool_rows)
    summary = summarize_pool(pool_rows)

    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    print(f"Input rows:   {len(raw_rows):,}")
    print(f"Removed rows: {removed:,}")
    print(f"Pool rows:    {len(pool_rows):,}")
    for group, count in sorted(summary.items()):
        print(f"  - {group}: {count:,}")

    print("\ncMedQA2 03 question pool: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
