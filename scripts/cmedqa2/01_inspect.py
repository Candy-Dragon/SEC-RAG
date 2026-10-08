"""cMedQA2 Step 1 - Inspect raw files.

INPUT:
  storage/datasets/raw/cMedQA2-master/question.csv
  storage/datasets/raw/cMedQA2-master/answer.csv

OUTPUT:
  storage/datasets/processed/cmedqa2/reports/raw_inspection.txt

RUN:
  python scripts/cmedqa2/01_inspect.py
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.data.cmedqa2.load import answer_file, load_questions, processed_dir, question_file  # noqa: E402
from sec_rag.paths import ensure_parent_dir  # noqa: E402


def count_csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in handle) - 1


def sample_rows(path: Path, limit: int = 3) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for _, row in zip(range(limit), reader)]


def main() -> int:
    print("cMedQA2 - 01 inspect raw")
    print("=" * 48)

    q_path = question_file()
    a_path = answer_file()
    print(f"Question file: {q_path}")
    print(f"Answer file:   {a_path}")

    question_count = count_csv_rows(q_path)
    answer_count = count_csv_rows(a_path)
    print(f"\nRows: questions={question_count:,}, answers={answer_count:,}")

    questions = load_questions()
    empty_questions = sum(1 for row in questions if not row["content"].strip())
    duplicate_ids = question_count - len({row["question_id"] for row in questions})
    lengths = Counter()
    for row in questions:
        length = len(row["content"])
        if length < 20:
            lengths["lt_20"] += 1
        elif length < 80:
            lengths["20_79"] += 1
        else:
            lengths["ge_80"] += 1

    print(f"Loaded questions: {len(questions):,}")
    print(f"Empty question text: {empty_questions}")
    print(f"Duplicate question_id rows: {duplicate_ids}")
    print("Question length buckets:", dict(lengths))

    print("\nSample questions:")
    for row in sample_rows(q_path, limit=3):
        preview = str(row.get("content", ""))[:120]
        print(f"  - id={row.get('question_id')} text={preview}")

    report_path = ensure_parent_dir(processed_dir() / "reports" / "raw_inspection.txt")
    report_path.write_text(
        "\n".join(
            [
                "cMedQA2 raw inspection",
                f"question_file={q_path}",
                f"answer_file={a_path}",
                f"question_rows={question_count}",
                f"answer_rows={answer_count}",
                f"loaded_questions={len(questions)}",
                f"empty_questions={empty_questions}",
                f"duplicate_question_ids={duplicate_ids}",
                f"length_buckets={dict(lengths)}",
            ]
        ),
        encoding="utf-8",
    )
    print(f"\nReport saved: {report_path}")
    print("\ncMedQA2 01 inspect: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
