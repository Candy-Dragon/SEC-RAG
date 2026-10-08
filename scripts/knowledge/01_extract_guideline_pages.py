"""Knowledge base Step 01: inspect PDFs and extract raw text page by page.

INPUT:
  storage/knowledge_base/documents/<disease>/*.pdf

OUTPUT:
  storage/knowledge_base/extracted/<disease>/<document_id>.pages.jsonl
  storage/knowledge_base/extracted/extraction_manifest.json

ACTION:
  Read every source PDF once. Save one uncleaned, page-traceable JSON record
  per page and record file identity, SHA-256, page counts, empty pages, errors,
  extracted character counts, and output locations in the manifest.

RUN:
  python scripts/knowledge/01_extract_guideline_pages.py
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.knowledge.page_extraction import (  # noqa: E402
    extract_all_guidelines,
    write_extraction_manifest,
)


def main() -> int:
    print("Knowledge base - 01 inspect and extract guideline PDFs")
    print("=" * 58)

    documents = extract_all_guidelines()
    if not documents:
        print("No PDF found under storage/knowledge_base/documents/<disease>/")
        return 1

    for document in documents:
        print(f"[{document.disease}] {document.source_file}")
        print(
            f"  pages={document.page_count}, extracted={document.extracted_page_count}, "
            f"empty={document.empty_page_count}, errors={document.error_page_count}, "
            f"characters={document.extracted_character_count:,}"
        )
        print(f"  output={document.output_relative_path}")

    manifest = write_extraction_manifest(documents)
    empty_pages = sum(document.empty_page_count for document in documents)
    error_pages = sum(document.error_page_count for document in documents)

    print(f"\nDocuments: {len(documents)}")
    print(f"Pages:     {sum(document.page_count for document in documents)}")
    print(f"Empty:     {empty_pages}")
    print(f"Errors:    {error_pages}")
    print(f"Manifest:  {manifest}")

    if error_pages:
        print("\nExtraction completed with page errors. Inspect the manifest.")
        return 1

    print("\nKnowledge base 01 inspection and extraction: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

