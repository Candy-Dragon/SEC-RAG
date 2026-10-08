"""Freeze disjoint cMedQA2 partitions and a small development run list.

Only single-disease questions are eligible for the present three-guideline
experiment. The nine hand-picked pipeline pilot questions remain separate.
No answerability or clinical labels are inferred here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sec_rag.data.cmedqa2.question_pool import default_pool_path


DEFAULT_OUTPUT = ROOT / "storage" / "datasets" / "processed" / "cmedqa2" / "splits" / "default"
FIELDS = ("qid", "question", "disease_scope", "source_dataset", "source_original_id")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def partition(rows: list[dict[str, str]], pilot_qids: set[str], seed: int, dev_per_disease: int):
    if dev_per_disease < 1:
        raise ValueError("dev_per_disease must be positive")
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    excluded = Counter()
    seen_qids: set[str] = set()
    seen_questions: set[str] = set()
    for row in rows:
        qid = row["qid"]
        question = row["question"].strip()
        if qid in seen_qids or question in seen_questions:
            raise ValueError(f"Duplicate qid or question in pool: {qid}")
        seen_qids.add(qid)
        seen_questions.add(question)
        if qid in pilot_qids:
            excluded["hand_picked_pilot"] += 1
            continue
        domains = json.loads(row["disease_domains_json"])
        if len(domains) != 1:
            excluded["multi_disease"] += 1
            continue
        groups[domains[0]["key"]].append({field: row[field] if field != "disease_scope" else domains[0]["key"] for field in FIELDS})
    if pilot_qids - seen_qids:
        raise ValueError(f"Pilot qids missing from pool: {sorted(pilot_qids - seen_qids)}")
    result = {name: [] for name in ("development", "validation", "test")}
    rng = random.Random(seed)
    for disease in sorted(groups):
        shuffled = sorted(groups[disease], key=lambda row: row["qid"])
        rng.shuffle(shuffled)
        # 70/15/15 is a predeclared operational split, not a claimed optimal ratio.
        n_dev = len(shuffled) * 70 // 100
        n_val = len(shuffled) * 15 // 100
        result["development"].extend(shuffled[:n_dev])
        result["validation"].extend(shuffled[n_dev:n_dev + n_val])
        result["test"].extend(shuffled[n_dev + n_val:])
    for name in result:
        result[name].sort(key=lambda row: row["qid"])
    sample = []
    sample_rng = random.Random(seed + 1)
    for disease in sorted(groups):
        disease_rows = [row for row in result["development"] if row["disease_scope"] == disease]
        if len(disease_rows) < dev_per_disease:
            raise ValueError(f"Not enough development questions in {disease}")
        sample.extend(sample_rng.sample(disease_rows, dev_per_disease))
    sample.sort(key=lambda row: row["qid"])
    partition_ids = [row["qid"] for name in result for row in result[name]]
    if len(partition_ids) != len(set(partition_ids)) or set(partition_ids) & pilot_qids:
        raise AssertionError("Split overlap detected")
    if len(partition_ids) + sum(excluded.values()) != len(rows):
        raise AssertionError("Split accounting failed")
    return result, sample, excluded


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260924)
    parser.add_argument("--dev-per-disease", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--pool", type=Path, help="Processed cMedQA2 question pool CSV")
    parser.add_argument("--exclude-config", type=Path, help="Optional JSON with questions:[{qid:...}] already used for development")
    args = parser.parse_args()
    pool_path = args.pool or default_pool_path()
    rows = load_rows(pool_path)
    pilot_qids = {item["qid"] for item in json.loads(args.exclude_config.read_text(encoding="utf-8"))["questions"]} if args.exclude_config else set()
    partitions, sample, excluded = partition(rows, pilot_qids, args.seed, args.dev_per_disease)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    files = {**partitions, "development_first_batch": sample}
    for name, selected in files.items():
        path = output / f"{name}.csv"
        if path.exists():
            raise FileExistsError(f"Split is frozen; refusing to overwrite {path}")
        write_csv(path, selected)
    manifest = {
        "purpose": "Disjoint, reproducible question partitions; not guideline answerability labels",
        "source_pool": {"path": str(pool_path), "sha256": sha256(pool_path), "rows": len(rows)},
        "excluded_pilot": {"path": str(args.exclude_config) if args.exclude_config else None, "sha256": sha256(args.exclude_config) if args.exclude_config else None, "qids": sorted(pilot_qids)},
        "excluded_counts": dict(excluded),
        "eligibility": "Exactly one disease domain in the preprocessed pool; pilot qids excluded",
        "split": "Within-disease seeded shuffle, floor(70%) development, floor(15%) validation, remainder test",
        "seed": args.seed,
        "development_first_batch_rule": f"Independent seeded random sample ({args.dev_per_disease} development rows per disease, seed+1); not a coverage or answerability sample",
        "files": {name: {"path": f"{name}.csv", "sha256": sha256(output / f"{name}.csv"), "rows": len(selected), "diseases": dict(Counter(row["disease_scope"] for row in selected))} for name, selected in files.items()},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output), "files": {name: len(selected) for name, selected in files.items()}, "excluded": dict(excluded)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
