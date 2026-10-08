"""Read different processed datasets without rewriting their source files."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path


def load_questions(path: Path, *, format: str, columns: dict, dataset: str) -> list[dict]:
    if format == "csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    elif format == "jsonl":
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    else:
        raise ValueError("Supported dataset formats: csv, jsonl; add an adapter for other formats")
    result, seen = [], set()
    for row in rows:
        item = {key: row[columns[key]] for key in ("qid", "question", "disease_scope")}
        if not all(isinstance(value, str) and value.strip() for value in item.values()):
            raise ValueError("Question ID, text and domain must be nonempty strings")
        item = {key: value.strip() for key, value in item.items()}
        if not re.fullmatch(r"[A-Za-z0-9_-]+", item["qid"]) or item["qid"] in seen:
            raise ValueError("Question IDs must be unique safe directory names")
        seen.add(item["qid"])
        item["source_dataset"] = dataset
        item["source_record"] = row
        result.append(item)
    if not result:
        raise ValueError("Dataset is empty")
    return result
