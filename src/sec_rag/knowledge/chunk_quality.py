"""Validate retrieval chunks and create deterministic review samples."""

from __future__ import annotations

import csv
import json
import statistics
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sec_rag.config import settings
from sec_rag.paths import ensure_parent_dir


SAMPLES_PER_DOCUMENT = 3
PREVIEW_LIMIT = 500


def chunks_root() -> Path:
    return settings.knowledge_path / "chunks"


def quality_root() -> Path:
    return settings.knowledge_path / "quality"


def chunk_paths() -> list[Path]:
    return sorted(chunks_root().glob("*/*.chunks.jsonl"), key=lambda p: p.as_posix().lower())


def load_chunk_config() -> dict[str, object]:
    path = settings.root / "configs" / "knowledge_chunking.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_chunks(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path}, line {line_number}: {exc}") from exc
    return records


def has_suspicious_unicode(text: str) -> bool:
    for character in text:
        category = unicodedata.category(character)
        if character in {"\ufffd", "\x00"} or category == "Co":
            return True
        if category == "Cc" and character not in "\n\r\t":
            return True
    return False


def likely_table_of_contents(
    text: str, page_start: int, maximum_page: int
) -> tuple[bool, str]:
    """Identify review candidates using explicit layout markers, not content."""
    compact = " ".join(text.split())
    early_page_limit = max(3, round(maximum_page * 0.10))
    if page_start <= early_page_limit and "目录" in compact[:80]:
        return True, "contains_catalogue_heading"
    if page_start <= early_page_limit and (
        compact.count("……") >= 2 or compact.count("......") >= 2
    ):
        return True, "multiple_dot_leaders"
    return False, ""


def deterministic_sample_indices(
    chunks: list[dict[str, object]], toc_indices: list[int]
) -> dict[int, set[str]]:
    """Choose at most three reproducible samples per document."""
    reasons: dict[int, set[str]] = defaultdict(set)
    count = len(chunks)
    if not count:
        return reasons
    positions = [0, round((count - 1) * 0.5), count - 1]
    for label, index in zip(("first", "middle", "last"), positions):
        reasons[index].add(f"{label}_chunk")
    if toc_indices:
        replacement = toc_indices[0]
        last_key = next(reversed(reasons))
        del reasons[last_key]
        reasons[replacement].add("possible_table_of_contents")
    return reasons


def analyze_chunks() -> tuple[dict[str, object], list[dict[str, object]]]:
    config = load_chunk_config()
    maximum = int(config["max_characters"])
    all_ids: list[str] = []
    documents: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []

    for path in chunk_paths():
        chunks = load_chunks(path)
        if not chunks:
            continue
        lengths = [int(chunk.get("character_count", 0)) for chunk in chunks]
        maximum_page = max(int(chunk.get("page_end", 0)) for chunk in chunks)
        toc_candidates: list[dict[str, object]] = []
        toc_indices: list[int] = []
        issue_counts: Counter[str] = Counter()

        for index, chunk in enumerate(chunks):
            text = str(chunk.get("text", ""))
            chunk_id = str(chunk.get("chunk_id", ""))
            all_ids.append(chunk_id)
            if not text.strip():
                issue_counts["empty_text"] += 1
            if len(text) != int(chunk.get("character_count", -1)):
                issue_counts["character_count_mismatch"] += 1
            if len(text) > maximum:
                issue_counts["over_maximum_length"] += 1
            page_numbers = [int(value) for value in chunk.get("page_numbers", [])]
            if not page_numbers:
                issue_counts["missing_page_numbers"] += 1
            elif (
                int(chunk.get("page_start", -1)) != min(page_numbers)
                or int(chunk.get("page_end", -1)) != max(page_numbers)
                or page_numbers != sorted(set(page_numbers))
            ):
                issue_counts["invalid_page_trace"] += 1
            if has_suspicious_unicode(text):
                issue_counts["suspicious_unicode"] += 1
            if not chunk_id or not chunk.get("document_id") or not chunk.get("source_file"):
                issue_counts["missing_identity_metadata"] += 1

            is_toc, reason = likely_table_of_contents(
                text, int(chunk.get("page_start", 0)), maximum_page
            )
            if is_toc:
                toc_indices.append(index)
                toc_candidates.append(
                    {
                        "chunk_id": chunk_id,
                        "chunk_index": chunk.get("chunk_index"),
                        "page_numbers": page_numbers,
                        "reason": reason,
                        "text_preview": text[:PREVIEW_LIMIT],
                    }
                )

        expected_indices = list(range(1, len(chunks) + 1))
        actual_indices = [int(chunk.get("chunk_index", -1)) for chunk in chunks]
        if actual_indices != expected_indices:
            issue_counts["nonsequential_chunk_index"] += 1

        sample_reasons = deterministic_sample_indices(chunks, toc_indices)
        for index, reasons in sorted(sample_reasons.items()):
            chunk = chunks[index]
            is_toc, toc_reason = likely_table_of_contents(
                str(chunk["text"]), int(chunk["page_start"]), maximum_page
            )
            review_rows.append(
                {
                    "review_status": "pending",
                    "sample_reasons": ";".join(sorted(reasons)),
                    "possible_table_of_contents": str(is_toc).lower(),
                    "toc_rule": toc_reason,
                    "disease": chunk["disease"],
                    "source_file": chunk["source_file"],
                    "document_id": chunk["document_id"],
                    "chunk_id": chunk["chunk_id"],
                    "chunk_index": chunk["chunk_index"],
                    "page_start": chunk["page_start"],
                    "page_end": chunk["page_end"],
                    "section_heading": chunk.get("section_heading", ""),
                    "character_count": chunk["character_count"],
                    "text": chunk["text"],
                    "review_notes": "",
                }
            )

        documents.append(
            {
                "document_id": chunks[0]["document_id"],
                "disease": chunks[0]["disease"],
                "source_file": chunks[0]["source_file"],
                "chunk_file": path.relative_to(chunks_root()).as_posix(),
                "chunk_count": len(chunks),
                "length_statistics": {
                    "minimum": min(lengths),
                    "median": round(statistics.median(lengths), 2),
                    "mean": round(statistics.mean(lengths), 2),
                    "maximum": max(lengths),
                },
                "structural_issue_count": sum(issue_counts.values()),
                "structural_issues": dict(issue_counts),
                "possible_table_of_contents_count": len(toc_candidates),
                "possible_table_of_contents": toc_candidates,
                "review_sample_count": len(sample_reasons),
            }
        )

    duplicate_counts = {key: value for key, value in Counter(all_ids).items() if value > 1}
    report = {
        "report_type": "guideline_chunk_quality",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Validate chunk structure and prepare deterministic manual-review samples",
        "automatic_toc_flags_are_review_candidates": True,
        "chunk_configuration": config,
        "checks": [
            "empty text",
            "configured maximum length",
            "stored character count",
            "unique chunk identity",
            "sequential chunk index",
            "page trace consistency",
            "required source metadata",
            "suspicious Unicode",
        ],
        "toc_candidate_rules": {
            "page_scope": "only the first max(3 pages, 10% of document pages)",
            "contains_catalogue_heading": "the first 80 characters contain 目录",
            "multiple_dot_leaders": "the chunk contains at least two Chinese or ASCII dot leaders",
        },
        "document_count": len(documents),
        "chunk_count": len(all_ids),
        "duplicate_chunk_id_count": len(duplicate_counts),
        "duplicate_chunk_ids": duplicate_counts,
        "structural_issue_count": sum(int(document["structural_issue_count"]) for document in documents),
        "possible_table_of_contents_count": sum(int(document["possible_table_of_contents_count"]) for document in documents),
        "review_sample_count": len(review_rows),
        "documents": documents,
    }
    return report, review_rows


def write_chunk_quality_outputs(
    report: dict[str, object], review_rows: list[dict[str, object]]
) -> tuple[Path, Path]:
    report_path = ensure_parent_dir(quality_root() / "chunk_quality_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    sample_path = ensure_parent_dir(quality_root() / "chunk_review_samples.csv")
    fieldnames = list(review_rows[0]) if review_rows else []
    try:
        handle = sample_path.open("w", encoding="utf-8-sig", newline="")
    except PermissionError:
        sample_path = quality_root() / "chunk_review_samples_updated.csv"
        handle = sample_path.open("w", encoding="utf-8-sig", newline="")
    with handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(review_rows)
    return report_path, sample_path
