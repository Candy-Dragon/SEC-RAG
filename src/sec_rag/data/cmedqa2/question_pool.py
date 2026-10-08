"""Build cMedQA2 question pool from candidates.

This step only:
  1) deduplicates candidates
  2) assigns stable experiment ids (qid)
  3) keeps the same justified fields as candidates

It does not add inferred clinical or evaluation labels.
"""

from __future__ import annotations

import csv
from pathlib import Path

from sec_rag.data.cmedqa2.candidates import default_candidates_output_path
from sec_rag.data.cmedqa2.load import processed_dir
from sec_rag.paths import ensure_parent_dir


POOL_FIELDS = [
    "qid",
    "candidate_id",
    "question",
    "disease_domains_json",
    "matched_keywords_json",
    "domain_count",
    "source_dataset",
    "source_original_id",
    "reference_answers_json",
    "reference_answer_count",
]


def default_candidates_path() -> Path:
    return default_candidates_output_path()


def default_pool_path() -> Path:
    return processed_dir() / "pool" / "question_pool_all.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def dedupe_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    seen_questions: set[str] = set()
    seen_candidate_ids: set[str] = set()
    deduped: list[dict[str, str]] = []
    removed = 0

    for row in rows:
        candidate_id = str(row.get("candidate_id", "")).strip()
        question = str(row.get("question", "")).strip()
        if not candidate_id or not question:
            removed += 1
            continue
        if candidate_id in seen_candidate_ids or question in seen_questions:
            removed += 1
            continue
        seen_candidate_ids.add(candidate_id)
        seen_questions.add(question)
        deduped.append(row)

    return deduped, removed


def build_question_pool(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    pool: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        pool.append(
            {
                "qid": f"CMEDQA2_{index:05d}",
                "candidate_id": row.get("candidate_id", ""),
                "question": row.get("question", ""),
                "disease_domains_json": row.get("disease_domains_json", "[]"),
                "matched_keywords_json": row.get("matched_keywords_json", "{}"),
                "domain_count": row.get("domain_count", "0"),
                "source_dataset": row.get("source_dataset", ""),
                "source_original_id": row.get("source_original_id", ""),
                "reference_answers_json": row.get("reference_answers_json", "[]"),
                "reference_answer_count": row.get("reference_answer_count", "0"),
            }
        )
    return pool


def write_question_pool(rows: list[dict[str, str]], output_path: Path | None = None) -> Path:
    path = ensure_parent_dir(output_path or default_pool_path())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=POOL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def summarize_pool(rows: list[dict[str, str]]) -> dict[str, int]:
    summary = {"single_domain": 0, "multi_domain": 0}
    for row in rows:
        key = "single_domain" if row.get("domain_count") == "1" else "multi_domain"
        summary[key] += 1
    return summary
