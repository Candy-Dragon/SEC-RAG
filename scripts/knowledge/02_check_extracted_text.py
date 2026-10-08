"""Knowledge base Step 02: check extracted page-text quality.

INPUT:
  storage/knowledge_base/extracted/<disease>/*.pages.jsonl

OUTPUT:
  storage/knowledge_base/quality/text_quality_report.json

ACTION:
  Flag length outliers and suspicious Unicode; identify repeated short lines
  and select representative pages for manual review. No text is modified.

RUN:
  python scripts/knowledge/02_check_extracted_text.py
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.knowledge.text_quality import (  # noqa: E402
    build_quality_report,
    write_quality_report,
)


def main() -> int:
    print("Knowledge base - 02 check extracted text")
    print("=" * 52)

    report = build_quality_report()
    if report["document_count"] == 0:
        print("No extracted page files found. Run step 01 first.")
        return 1

    for document in report["documents"]:
        repeated_count = len(document["repeated_line_candidates"])
        print(f"[{document['disease']}] {document['source_file']}")
        print(
            f"  pages={document['page_count']}, "
            f"flagged_pages={document['flagged_page_count']}, "
            f"repeated_line_candidates={repeated_count}"
        )

    output_path = write_quality_report(report)
    print(f"\nDocuments:     {report['document_count']}")
    print(f"Pages:         {report['page_count']}")
    print(f"Flagged pages: {report['flagged_page_count']}")
    print(f"Report:        {output_path}")
    print("\nThese flags request review; they do not mean the page is incorrect.")
    print("Knowledge base 02 text-quality check: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

