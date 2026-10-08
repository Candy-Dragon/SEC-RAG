"""Knowledge base Step 03: conservatively clean extracted page text.

INPUT:
  storage/knowledge_base/extracted/<disease>/*.pages.jsonl

OUTPUT:
  storage/knowledge_base/cleaned/<disease>/*.clean.pages.jsonl
  storage/knowledge_base/cleaned/cleaning_manifest.json

ACTION:
  Remove confirmed technical noise while preserving page identity and an
  audit record of every removed character and line. Raw files are unchanged.

RUN:
  python scripts/knowledge/03_clean_extracted_text.py
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.knowledge.text_cleaning import clean_all_pages  # noqa: E402


def main() -> int:
    print("Knowledge base - 03 clean extracted text")
    print("=" * 48)
    documents, manifest = clean_all_pages()
    if not documents:
        print("No extracted pages found. Run steps 01 and 02 first.")
        return 1

    for document in documents:
        print(f"[{document['disease']}] {document['source_file']}")
        print(
            f"  pages={document['page_count']}, "
            f"removed_characters={document['removed_technical_character_count']}, "
            f"removed_lines={document['removed_line_count']}"
        )
        print(f"  output={document['output_file']}")

    print(f"\nDocuments:          {manifest['document_count']}")
    print(f"Pages:              {manifest['page_count']}")
    print(f"Raw characters:     {manifest['raw_character_count']:,}")
    print(f"Clean characters:   {manifest['clean_character_count']:,}")
    print(f"Technical removed:  {manifest['removed_technical_character_count']:,}")
    print(f"Lines removed:      {manifest['removed_line_count']:,}")
    print("Manifest:           storage/knowledge_base/cleaned/cleaning_manifest.json")
    print("\nKnowledge base 03 conservative cleaning: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
