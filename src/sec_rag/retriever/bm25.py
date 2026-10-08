from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from sec_rag.config import settings
from sec_rag.method.constants import LOADED_IMPLEMENTATION_PROVENANCE, METHOD_CONFIG_PATH, VERSION
from sec_rag.utils.stage_runtime import now, sha, write_json


def stage01_retrieval(
    question: str,
    *,
    question_id: str,
    source_dataset: str,
    disease_scope: str,
    top_n: int = 5,
    output_path: Path,
) -> dict[str, Any]:
    if not question.strip() or not question_id.strip():
        raise ValueError("question and question_id are required")
    if top_n < 1:
        raise ValueError("top_n must be positive")
    scope_path = settings.root / settings.experiment_scope_path
    scope_configuration = json.loads(scope_path.read_text(encoding="utf-8"))
    allowed_diseases = {str(item) for item in scope_configuration["included_diseases"]}
    if disease_scope not in allowed_diseases:
        raise ValueError(
            f"disease_scope {disease_scope!r} is outside the controlled experiment scope: "
            f"{sorted(allowed_diseases)}"
        )
    from sec_rag.knowledge.bm25_index import config_path, file_sha256, index_root, load_config
    from sec_rag.knowledge.bm25_search import GuidelineBM25Retriever

    retriever = GuidelineBM25Retriever()
    results = retriever.search(question.strip(), top_k=top_n, disease=disease_scope)
    if len(results) != top_n:
        raise ValueError(f"BM25 returned {len(results)} results; expected {top_n}")
    ids = [str(item["chunk_id"]) for item in results]
    if len(set(ids)) != len(ids):
        raise ValueError("BM25 returned duplicate chunk IDs")
    record = {
        "created_at_utc": now(), "method_version": VERSION, "stage": "01_retrieval", "status": "completed",
        "input": {"question_id": question_id, "source_dataset": source_dataset, "question": question.strip(), "disease_scope": disease_scope, "top_n": top_n},
        "method_configuration": {"path": METHOD_CONFIG_PATH.relative_to(settings.root).as_posix(), "sha256": sha(METHOD_CONFIG_PATH), "configuration": json.loads(METHOD_CONFIG_PATH.read_text(encoding="utf-8"))},
        "experiment_scope": {"path": scope_path.relative_to(settings.root).as_posix(), "sha256": sha(scope_path), "configuration": scope_configuration},
        # These hashes are captured when the Python process imports the code.
        # A process that remains alive while files are edited therefore records
        # the code it actually loaded instead of the newer bytes on disk.
        "implementation_provenance": LOADED_IMPLEMENTATION_PROVENANCE,
        "retrieval_policy": "Shared BM25 Top-N for all RAG methods; no LLM reranking.",
        "retrieval_configuration": {
            "configuration_path": config_path().relative_to(settings.root).as_posix(),
            "configuration_sha256": sha(config_path()),
            "configuration": load_config(),
            "corpus_path": (index_root() / "corpus.jsonl").relative_to(settings.root).as_posix(),
            "corpus_sha256": file_sha256(index_root() / "corpus.jsonl"),
            "index_manifest_path": (index_root() / "index_manifest.json").relative_to(settings.root).as_posix(),
            "index_manifest_sha256": file_sha256(index_root() / "index_manifest.json"),
        },
        "retrieval_results": results,
        "validation": {"valid": True, "result_count": len(results), "unique_chunk_ids": True, "continuous_ranks": [x["rank"] for x in results] == list(range(1, top_n + 1)), "disease_scope_match": all(x["disease"] == disease_scope for x in results)},
    }
    write_json(output_path, record)
    return record
