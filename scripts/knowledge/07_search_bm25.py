"""Knowledge base Step 07: run an interpretable BM25 search.

RUN:
  python scripts/knowledge/07_search_bm25.py "糖尿病患者如何控制血糖"
  python scripts/knowledge/07_search_bm25.py "高血压诊断标准" --top-k 3
  python scripts/knowledge/07_search_bm25.py "肺癌筛查" --disease lung_cancer
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.knowledge.bm25_search import GuidelineBM25Retriever  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search clinical guideline chunks with BM25")
    parser.add_argument("query", help="Chinese medical question")
    parser.add_argument("--top-k", type=int, default=5, help="number of results")
    parser.add_argument("--disease", help="optional disease folder key")
    parser.add_argument("--json", action="store_true", help="print full results as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    retriever = GuidelineBM25Retriever()
    results = retriever.search(args.query, top_k=args.top_k, disease=args.disease)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    print(f"Query: {args.query}")
    print(f"Tokens: {results[0]['query_tokens'] if results else []}")
    print(f"Results: {len(results)}")
    print("=" * 72)
    for result in results:
        print(f"#{result['rank']} score={result['score']} disease={result['disease']}")
        print(f"Source: {result['source_file']}")
        print(f"Pages:  {result['page_start']}-{result['page_end']}")
        print(f"Section:{result['section_heading'] or '(not detected)'}")
        print(f"Chunk:  {result['chunk_id']}")
        print(f"Text:   {result['text'][:500]}")
        print("-" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
