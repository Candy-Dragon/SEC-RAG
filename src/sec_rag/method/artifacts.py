"""Integrity ledger for completed experiment artifacts (no model calls)."""
import json
from sec_rag.utils.stage_runtime import sha, write_json


def verify_artifacts(directory):
    ledger = directory / "artifacts.json"
    if not ledger.exists():
        if any(directory.glob("0*.json")) or any((directory / "baselines").glob("*.json")):
            raise ValueError("Existing artifacts lack an integrity ledger; preserve them and choose a new output_dir")
        return {}
    entries = json.loads(ledger.read_text(encoding="utf-8"))
    for relative, digest in entries.items():
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file() or sha(path) != digest:
            raise ValueError(f"Saved artifact missing or modified: {relative}; preserve this run and choose a new output_dir")
    actual = {p.relative_to(directory).as_posix() for p in tracked_files(directory)}
    if actual != set(entries):
        raise ValueError("Untracked experiment artifacts detected; preserve this run and choose a new output_dir")
    return entries


def tracked_files(directory):
    return list(directory.glob("0*.json")) + list(directory.glob("run_manifest.json")) + list((directory / "baselines").glob("*.json"))


def seal_artifacts(directory):
    write_json(directory / "artifacts.json", {p.relative_to(directory).as_posix(): sha(p) for p in tracked_files(directory)})
