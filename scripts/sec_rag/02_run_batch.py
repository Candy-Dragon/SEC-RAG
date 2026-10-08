"""Create and run a reproducible single-disease cMedQA2 SEC-RAG v5 batch."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.config import settings  # noqa: E402
from sec_rag.data.cmedqa2.question_pool import default_pool_path  # noqa: E402
from sec_rag.method.runner import run_question  # noqa: E402
from sec_rag.method.v5 import VERSION, write_json  # noqa: E402


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pool(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def select_rows(rows: list[dict[str, str]], per_disease: int, seed: int) -> list[dict[str, str]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        domains = json.loads(row["disease_domains_json"])
        if len(domains) != 1:
            continue
        groups.setdefault(domains[0]["key"], []).append(row)
    rng = random.Random(seed)
    selected = []
    for disease in sorted(groups):
        candidates = sorted(groups[disease], key=lambda row: row["qid"])
        if len(candidates) < per_disease:
            raise ValueError(f"Disease {disease} has fewer than {per_disease} questions")
        selected.extend(rng.sample(candidates, per_disease))
    return sorted(selected, key=lambda row: row["qid"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-disease", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260920)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--resume", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pool_path = default_pool_path()
    if args.resume:
        batch_dir = args.resume.resolve()
        manifest_path = batch_dir / "batch_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["method_version"] != VERSION:
            raise ValueError("Batch method version does not match")
    else:
        rows = select_rows(load_pool(pool_path), args.per_disease, args.seed)
        batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]
        batch_dir = settings.storage_path / "experiments" / "testing" / "small_batch" / VERSION / batch_id
        batch_dir.mkdir(parents=True, exist_ok=False)
        manifest_path = batch_dir / "batch_manifest.json"
        manifest = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "batch_id": batch_id,
            "method_version": VERSION,
            "selection": {"pool_path": pool_path.relative_to(ROOT).as_posix(), "pool_sha256": file_sha(pool_path), "per_disease": args.per_disease, "seed": args.seed, "top_n": args.top_n},
            "questions": [],
        }
        for row in rows:
            disease = json.loads(row["disease_domains_json"])[0]["key"]
            manifest["questions"].append({
                "qid": row["qid"], "question": row["question"], "disease_scope": disease,
                "source_dataset": row["source_dataset"], "source_original_id": row["source_original_id"],
                "reference_answers_json": row["reference_answers_json"],
                "reference_answer_usage": "Stored in batch manifest only; never passed to SEC-RAG stages.",
                "status": "pending", "run_manifest": None, "error": None,
            })
        write_json(manifest_path, manifest)
    top_n = int(manifest["selection"]["top_n"])
    for item in manifest["questions"]:
        qdir = batch_dir / "questions" / item["qid"]
        try:
            run_manifest = run_question(question=item["question"], question_id=item["qid"], source_dataset=item["source_dataset"], disease_scope=item["disease_scope"], top_n=top_n, output_dir=qdir)
            item["status"] = "completed"
            item["run_manifest"] = (qdir / "run_manifest.json").relative_to(ROOT).as_posix()
            item["run_manifest_sha256"] = file_sha(qdir / "run_manifest.json")
            item["error"] = None
        except Exception as exc:
            item["status"] = "failed"
            item["error"] = {"type": type(exc).__name__, "message": str(exc)}
        write_json(manifest_path, manifest)
    summary = {
        "batch_id": manifest["batch_id"], "method_version": VERSION,
        "question_count": len(manifest["questions"]),
        "completed_count": sum(item["status"] == "completed" for item in manifest["questions"]),
        "failed_count": sum(item["status"] == "failed" for item in manifest["questions"]),
        "questions": [{"qid": item["qid"], "disease_scope": item["disease_scope"], "status": item["status"], "error": item["error"]} for item in manifest["questions"]],
    }
    write_json(batch_dir / "batch_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
