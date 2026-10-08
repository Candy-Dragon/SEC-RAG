"""Search the persisted guideline corpus with BM25Okapi."""

from __future__ import annotations

from rank_bm25 import BM25Okapi

from sec_rag.knowledge.bm25_index import load_bm25_corpus, load_config, tokenize


class GuidelineBM25Retriever:
    def __init__(self) -> None:
        self.config = load_config()
        self.corpus = load_bm25_corpus()
        tokenized_corpus = [list(record["tokens"]) for record in self.corpus]
        self.model = BM25Okapi(
            tokenized_corpus,
            k1=float(self.config["k1"]),
            b=float(self.config["b"]),
        )

    def search(
        self, query: str, top_k: int | None = None, disease: str | None = None
    ) -> list[dict[str, object]]:
        query_tokens = tokenize(query)
        if not query_tokens:
            raise ValueError("Query contains no searchable Chinese, Latin, or numeric token.")
        limit = top_k or int(self.config["default_top_k"])
        scores = self.model.get_scores(query_tokens)
        candidates = [
            (index, float(score))
            for index, score in enumerate(scores)
            if disease is None or self.corpus[index]["disease"] == disease
        ]
        candidates.sort(key=lambda item: (-item[1], str(self.corpus[item[0]]["chunk_id"])))
        results: list[dict[str, object]] = []
        for rank, (index, score) in enumerate(candidates[:limit], start=1):
            source = self.corpus[index]
            results.append(
                {
                    "rank": rank,
                    "score": round(score, 6),
                    "query_tokens": query_tokens,
                    "chunk_id": source["chunk_id"],
                    "document_id": source["document_id"],
                    "disease": source["disease"],
                    "source_file": source["source_file"],
                    "page_start": source["page_start"],
                    "page_end": source["page_end"],
                    "section_heading": source.get("section_heading", ""),
                    "text": source["text"],
                }
            )
        return results
