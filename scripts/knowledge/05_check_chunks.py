"""Knowledge base Step 05: validate chunks and create review samples.

INPUT:
  storage/knowledge_base/chunks/<disease>/*.chunks.jsonl
  configs/knowledge_chunking.json

OUTPUT:
  storage/knowledge_base/quality/chunk_quality_report.json
  storage/knowledge_base/quality/chunk_review_samples.csv

RUN:
  python scripts/knowledge/05_check_chunks.py
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.knowledge.chunk_quality import (  # noqa: E402
    analyze_chunks,
    write_chunk_quality_outputs,
)


def main() -> int:
    print("Knowledge base - 05 check retrieval chunks")
    print("=" * 50)
    report, review_rows = analyze_chunks()
    if report["document_count"] == 0:
        print("No chunks found. Run step 04 first.")
        return 1
    report_path, sample_path = write_chunk_quality_outputs(report, review_rows)
    for document in report["documents"]:
        print(f"[{document['disease']}] {document['source_file']}")
        print(
            f"  chunks={document['chunk_count']}, "
            f"structural_issues={document['structural_issue_count']}, "
            f"possible_toc={document['possible_table_of_contents_count']}, "
            f"review_samples={document['review_sample_count']}"
        )
    print(f"\nDocuments:         {report['document_count']}")
    print(f"Chunks:            {report['chunk_count']}")
    print(f"Structural issues: {report['structural_issue_count']}")
    print(f"Duplicate IDs:     {report['duplicate_chunk_id_count']}")
    print(f"Possible TOC:      {report['possible_table_of_contents_count']}")
    print(f"Review samples:    {report['review_sample_count']}")
    print(f"Report:            {report_path}")
    print(f"Samples:           {sample_path}")
    if report["structural_issue_count"] or report["duplicate_chunk_id_count"]:
        print("\nChunk quality check found structural errors. Inspect the report.")
        return 1
    if report["possible_table_of_contents_count"]:
        print("\nAutomatic checks passed. TOC candidates still require review.")
    else:
        print("\nAutomatic checks passed. No remaining TOC candidate was detected.")
    print("Knowledge base 05 chunk-quality check: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
