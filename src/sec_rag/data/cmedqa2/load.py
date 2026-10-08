"""Load cMedQA2 raw CSV files. 只读取，不处理。用来给流水线调用"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from sec_rag.config import settings


DATASET_KEY = "cmedqa2"
RAW_DIR_NAME = "cMedQA2-master"


def raw_dir() -> Path:
    return settings.datasets_raw / RAW_DIR_NAME


def processed_dir() -> Path:
    return settings.processed_for(DATASET_KEY)


def question_file() -> Path:
    for name in ("question.csv", "questions.csv"):
        path = raw_dir() / name
        if path.exists():
            return path
    raise FileNotFoundError(f"Missing question CSV under {raw_dir()}")


def answer_file() -> Path:
    for name in ("answer.csv", "answers.csv"):
        path = raw_dir() / name
        if path.exists():
            return path
    raise FileNotFoundError(f"Missing answer CSV under {raw_dir()}")


def load_questions() -> list[dict[str, str]]:
    path = question_file()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            question_id = str(row.get("question_id", "")).strip()
            content = str(row.get("content", "")).strip()
            if question_id and content:
                rows.append({"question_id": question_id, "content": content})
        return rows


def load_answers_by_question() -> dict[str, list[dict[str, str]]]:
    """Load every original answer and preserve its original answer id."""
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    path = answer_file()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            question_id = str(row.get("question_id", "")).strip()
            answer_id = str(row.get("ans_id", row.get("answer_id", ""))).strip()
            content = str(row.get("content", "")).strip()
            if question_id and content:
                grouped[question_id].append(
                    {"answer_id": answer_id, "content": content}
                )
    return grouped
