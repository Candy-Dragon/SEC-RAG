"""Build cMedQA2 disease-domain candidate pool. 从 cMedQA2 原始问答，筛选并生成疾病候选样本

The output keeps provenance, the exact disease terms used for filtering,
and every original cMedQA2 answer. It adds no clinical or evaluation labels.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from sec_rag.data.cmedqa2.load import (
    load_answers_by_question,
    load_questions,
    processed_dir,
)
from sec_rag.data.diseases import detect_diseases
from sec_rag.paths import ensure_parent_dir


OUTPUT_FIELDS = [
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


def default_candidates_output_path() -> Path:
    return processed_dir() / "candidates" / "candidates_all.csv"


def build_candidates() -> list[dict[str, str]]:
    questions = load_questions()
    answers_by_question = load_answers_by_question()
    candidates: list[dict[str, str]] = []

    for row in questions:
        question = row["content"]
        matches = detect_diseases(question)
        if not matches:
            continue

        question_id = row["question_id"]
        answers = answers_by_question.get(question_id, [])
        candidates.append(
            {
                "candidate_id": f"CMEDQA2_{question_id}",
                "question": question,
                "disease_domains_json": json.dumps(
                    [
                        {"key": match.disease.key, "label": match.disease.label}
                        for match in matches
                    ],
                    ensure_ascii=False,
                ),
                "matched_keywords_json": json.dumps(
                    {
                        match.disease.key: list(match.matched_keywords)
                        for match in matches
                    },
                    ensure_ascii=False,
                ),
                "domain_count": str(len(matches)),
                "source_dataset": "cMedQA2",
                "source_original_id": question_id,
                "reference_answers_json": json.dumps(answers, ensure_ascii=False),
                "reference_answer_count": str(len(answers)),
            }
        )

    return candidates


def write_candidates(rows: list[dict[str, str]], output_path: Path | None = None) -> Path:
    path = ensure_parent_dir(output_path or default_candidates_output_path())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def summarize_by_disease(rows: list[dict[str, str]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for row in rows:
        for disease in json.loads(row["disease_domains_json"]):
            key = disease["key"]
            summary[key] = summary.get(key, 0) + 1
    return summary
