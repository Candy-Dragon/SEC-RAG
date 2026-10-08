"""Build and load a transparent BM25 corpus from guideline chunks."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import jieba

from sec_rag.config import settings
from sec_rag.paths import ensure_parent_dir


SEARCHABLE_TOKEN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def chunks_root() -> Path:
    return settings.knowledge_path / "chunks"


def index_root() -> Path:
    return settings.knowledge_path / "indexes" / "bm25"


def config_path() -> Path:
    return settings.root / "configs" / "bm25.json"


def load_config() -> dict[str, object]:
    return json.loads(config_path().read_text(encoding="utf-8"))


def tokenize(text: str) -> list[str]:
    """Tokenize Chinese in jieba search mode and discard punctuation-only tokens."""
    return [
        token
        for token in (part.strip().lower() for part in jieba.cut_for_search(text))
        if token and SEARCHABLE_TOKEN.search(token)
    ]


def chunk_paths() -> list[Path]:
    return sorted(chunks_root().glob("*/*.chunks.jsonl"), key=lambda p: p.as_posix().lower())


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def build_bm25_corpus() -> tuple[Path, Path, dict[str, object]]:
    config = load_config()
    source_files = chunk_paths()
    corpus_path = ensure_parent_dir(index_root() / "corpus.jsonl")
    document_counts: dict[str, int] = {}
    disease_counts: dict[str, int] = {}
    token_counts: list[int] = []
    chunk_count = 0

    with corpus_path.open("w", encoding="utf-8", newline="\n") as output:
        for source_path in source_files:
            with source_path.open("r", encoding="utf-8") as source:
                for line_number, line in enumerate(source, start=1):
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ValueError(
                            f"Invalid JSON in {source_path}, line {line_number}: {exc}"
                        ) from exc
                    tokens = tokenize(str(chunk["text"]))
                    if not tokens:
                        raise ValueError(f"Chunk has no searchable tokens: {chunk['chunk_id']}")
                    record = {**chunk, "tokens": tokens, "token_count": len(tokens)}
                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
                    chunk_count += 1
                    token_counts.append(len(tokens))
                    document_id = str(chunk["document_id"])
                    disease = str(chunk["disease"])
                    document_counts[document_id] = document_counts.get(document_id, 0) + 1
                    disease_counts[disease] = disease_counts.get(disease, 0) + 1

    manifest = {
        "manifest_type": "guideline_bm25_corpus",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "configuration_file": config_path().relative_to(settings.root).as_posix(),
        "configuration": config,
        "source_chunk_files": [
            {
                "path": path.relative_to(chunks_root()).as_posix(),
                "sha256": file_sha256(path),
            }
            for path in source_files
        ],
        "corpus_file": corpus_path.relative_to(index_root()).as_posix(),
        "corpus_sha256": file_sha256(corpus_path),
        "chunk_count": chunk_count,
        "document_count": len(document_counts),
        "disease_counts": dict(sorted(disease_counts.items())),
        "minimum_tokens": min(token_counts) if token_counts else 0,
        "maximum_tokens": max(token_counts) if token_counts else 0,
        "mean_tokens": round(sum(token_counts) / len(token_counts), 2) if token_counts else 0,
        "dependencies": {
            "jieba": jieba.__version__,
            "rank_bm25": __import__("importlib.metadata").metadata.version("rank-bm25"),
        },
    }
    manifest_path = index_root() / "index_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return corpus_path, manifest_path, manifest


def load_bm25_corpus() -> list[dict[str, object]]:
    path = index_root() / "corpus.jsonl"
    if not path.exists():
        raise FileNotFoundError("BM25 corpus not found. Run knowledge step 06 first.")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
