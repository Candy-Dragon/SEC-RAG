"""Knowledge base Step 04: build traceable retrieval chunks.

INPUT:
  storage/knowledge_base/cleaned/<disease>/*.clean.pages.jsonl
  configs/knowledge_chunking.json

OUTPUT:
  storage/knowledge_base/chunks/<disease>/*.chunks.jsonl
  storage/knowledge_base/chunks/chunk_manifest.json

RUN:
  python scripts/knowledge/04_build_chunks.py
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.knowledge.chunking import build_all_chunks  # noqa: E402


def main() -> int:
    print("Knowledge base - 04 build retrieval chunks")
    print("=" * 50)
    documents, manifest = build_all_chunks()
    if not documents:
        print("No cleaned pages found. Run steps 01-03 first.")
        return 1
    config = manifest["configuration"]
    print(
        f"Method={config['method']}, max={config['max_characters']}, "
        f"overlap={config['overlap_characters']} characters\n"
    )
    for document in documents:
        print(f"[{document['disease']}] {document['source_file']}")
        print(
            f"  source_pages={document['source_page_count']}, "
            f"indexed_pages={document['indexed_page_count']}, "
            f"chunks={document['chunk_count']}, "
            f"length={document['minimum_chunk_characters']}-"
            f"{document['maximum_chunk_characters']}, "
            f"mean={document['mean_chunk_characters']}"
        )
        print(f"  output={document['output_file']}")
    print(f"\nDocuments: {manifest['document_count']}")
    print(f"Source pages:  {manifest['source_page_count']}")
    print(f"Indexed pages: {manifest['indexed_page_count']}")
    print(f"Chunks:    {manifest['chunk_count']}")
    print("Manifest:  storage/knowledge_base/chunks/chunk_manifest.json")
    print("\nKnowledge base 04 chunking: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
