"""cMedQA2 Step 2 - Build disease candidates.

INPUT:
  storage/datasets/raw/cMedQA2-master/question.csv
  storage/datasets/raw/cMedQA2-master/answer.csv

OUTPUT:
  storage/datasets/processed/cmedqa2/candidates/candidates_all.csv

RUN:
  python scripts/cmedqa2/02_build_candidates.py
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.data.cmedqa2.candidates import (  # noqa: E402
    build_candidates,
    summarize_by_disease,
    write_candidates,
)


def main() -> int:
    print("cMedQA2 - 02 build candidates")
    print("=" * 48)

    rows = build_candidates()
    output_path = write_candidates(rows)
    summary = summarize_by_disease(rows)

    print(f"Output: {output_path}")
    print(f"Total candidates: {len(rows):,}")
    for disease, count in sorted(summary.items()):
        print(f"  - {disease}: {count:,}")

    if len(rows) == 0:
        print("\nNo candidates found. Check disease keywords or raw CSV files.")
        return 1

    print("\ncMedQA2 02 candidates: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
