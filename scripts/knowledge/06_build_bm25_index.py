"""Knowledge base Step 06: build the transparent BM25 corpus index.

INPUT:
  storage/knowledge_base/chunks/<disease>/*.chunks.jsonl
  configs/bm25.json

OUTPUT:
  storage/knowledge_base/indexes/bm25/corpus.jsonl
  storage/knowledge_base/indexes/bm25/index_manifest.json

RUN:
  python scripts/knowledge/06_build_bm25_index.py
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.knowledge.bm25_index import build_bm25_corpus  # noqa: E402


def main() -> int:
    print("Knowledge base - 06 build BM25 index")
    print("=" * 46)
    corpus_path, manifest_path, manifest = build_bm25_corpus()
    if manifest["chunk_count"] == 0:
        print("No chunks found. Run steps 04-05 first.")
        return 1
    print(f"Documents:   {manifest['document_count']}")
    print(f"Chunks:      {manifest['chunk_count']}")
    print(f"By disease:  {manifest['disease_counts']}")
    print(
        f"Token count: {manifest['minimum_tokens']}-"
        f"{manifest['maximum_tokens']}, mean={manifest['mean_tokens']}"
    )
    print(f"Corpus:      {corpus_path}")
    print(f"Manifest:    {manifest_path}")
    print("\nKnowledge base 06 BM25 index: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
