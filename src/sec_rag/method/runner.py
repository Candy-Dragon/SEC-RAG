"""Run and resume the six-stage SEC-RAG v5 pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from sec_rag.config import settings
from sec_rag.method.constants import VERSION
from sec_rag.utils.stage_runtime import now, sha, write_json
from sec_rag.method.components import resolve_components, execute, validate_record

STAGE_NAMES = (
    "01_retrieval", "02_evidence_units", "03_integrity", "04_applicability",
    "05_coverage", "06_final_answer",
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def embedded_file_hashes_match(value: Any) -> bool:
    """Reject cached stages when any recorded project file has changed."""
    if isinstance(value, list):
        return all(embedded_file_hashes_match(item) for item in value)
    if not isinstance(value, dict):
        return True
    if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
        tracked = settings.root / value["path"]
        if not tracked.exists() or sha(tracked) != value["sha256"]:
            return False
    return all(embedded_file_hashes_match(item) for item in value.values())


def completed_stage(
    path: Path,
    expected_stage: str,
    expected_input: dict[str, Any],
    source_path: Path | None,
) -> bool:
    if not path.exists():
        return False
    try:
        value = read_json(path)
    except (OSError, json.JSONDecodeError):
        return False
    basic_match = (
        value.get("status") == "completed"
        and value.get("stage") == expected_stage
        and value.get("input") == expected_input
        and value.get("method_version") == VERSION
    )
    if not basic_match:
        return False
    if not embedded_file_hashes_match(value):
        return False
    if source_path is not None:
        source_record = value.get("source_record")
        return (
            source_path.exists()
            and isinstance(source_record, dict)
            and source_record.get("path") == source_path.relative_to(settings.root).as_posix()
            and source_record.get("sha256") == sha(source_path)
        )
    # Stage 01 has no upstream stage. Its embedded configuration and index
    # provenance must still match the files currently on disk.
    try:
        tracked = [
            value["method_configuration"],
            value["experiment_scope"],
            *value["implementation_provenance"],
            {
                "path": value["retrieval_configuration"]["configuration_path"],
                "sha256": value["retrieval_configuration"]["configuration_sha256"],
            },
            {
                "path": value["retrieval_configuration"]["corpus_path"],
                "sha256": value["retrieval_configuration"]["corpus_sha256"],
            },
            {
                "path": value["retrieval_configuration"]["index_manifest_path"],
                "sha256": value["retrieval_configuration"]["index_manifest_sha256"],
            },
        ]
        return all(
            (settings.root / item["path"]).exists()
            and sha(settings.root / item["path"]) == item["sha256"]
            for item in tracked
        )
    except (KeyError, TypeError):
        return False


def failure_record(stage: str, input_record: dict[str, Any], error: Exception, source_path: Path | None) -> dict[str, Any]:
    record = {
        "created_at_utc": now(), "method_version": VERSION, "stage": stage, "status": "failed",
        "input": input_record,
        "source_record": ({"path": source_path.relative_to(settings.root).as_posix(), "sha256": sha(source_path)} if source_path and source_path.exists() else None),
        "error": {"type": type(error).__name__, "message": str(error)},
    }
    trace = getattr(error, "trace", None)
    if isinstance(trace, dict):
        record["failed_model_trace"] = trace
    return record


def run_question(
    *,
    question: str,
    question_id: str,
    source_dataset: str,
    disease_scope: str,
    output_dir: Path,
    top_n: int = 5,
    components: dict[str, str] | None = None,
) -> dict[str, Any]:
    resolved = resolve_components(components)
    selection = {stage: info for stage, (_, info) in resolved.items()}
    output_dir.mkdir(parents=True, exist_ok=True)
    input_record = {
        "question_id": question_id, "source_dataset": source_dataset,
        "question": question.strip(), "disease_scope": disease_scope, "top_n": top_n,
    }
    manifest_path = output_dir / "run_manifest.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else {
        "created_at_utc": now(), "method_version": VERSION, "input": input_record,
        "status": "pending", "stages": {}, "error": None,
    }
    if manifest.get("method_version") != VERSION:
        raise ValueError("Existing run belongs to a different SEC-RAG method version; choose a new output directory")
    if manifest["input"] != input_record:
        raise ValueError("Existing run manifest does not match the requested input")
    if manifest.get("components") not in (None, selection):
        raise ValueError("Stage implementations changed; choose a new output directory")
    for stage, entry in manifest.get("stages", {}).items():
        if entry.get("status") == "completed" and stage in STAGE_NAMES:
            saved = output_dir / f"{stage}.json"
            if not saved.is_file() or sha(saved) != entry.get("sha256"):
                raise ValueError(f"Saved stage missing or modified: {stage}; choose a new output directory")
    manifest["components"] = selection
    # Drop stage entries from retired method versions so an old verification
    # or repair record can never be mistaken for part of the six-stage method.
    manifest["stages"] = {
        name: value for name, value in manifest.get("stages", {}).items()
        if name in STAGE_NAMES
    }
    manifest.pop("final_record", None)

    paths = {name: output_dir / f"{name}.json" for name in STAGE_NAMES}
    calls = []
    for index, stage in enumerate(STAGE_NAMES):
        previous = paths[STAGE_NAMES[index - 1]] if index else None
        calls.append((stage, lambda stage=stage, previous=previous: execute(stage, resolved, input_record, paths[stage], previous), previous))
    manifest["status"] = "running"
    manifest["error"] = None
    write_json(manifest_path, manifest)
    for stage, call, source_path in calls:
        path = paths[stage]
        try:
            cached = read_json(path) if path.exists() else {}
            if cached:
                validate_record(cached, stage, input_record)
        except (OSError, ValueError, TypeError, KeyError):
            cached = {}
        if cached.get("component") == selection[stage] and completed_stage(path, stage, input_record, source_path):
            manifest["stages"][stage] = {"status": "completed", "path": path.relative_to(settings.root).as_posix(), "sha256": sha(path), "resumed": True}
            write_json(manifest_path, manifest)
            continue
        try:
            record = call()
            validate_record(record, stage, input_record)
            manifest["stages"][stage] = {"status": "completed", "path": path.relative_to(settings.root).as_posix(), "sha256": sha(path), "resumed": False}
            write_json(manifest_path, manifest)
        except Exception as exc:
            failed = failure_record(stage, input_record, exc, source_path)
            write_json(path, failed)
            manifest["status"] = "failed"
            manifest["error"] = {"stage": stage, "type": type(exc).__name__, "message": str(exc)}
            manifest["stages"][stage] = {"status": "failed", "path": path.relative_to(settings.root).as_posix(), "sha256": sha(path)}
            write_json(manifest_path, manifest)
            raise
    manifest["status"] = "completed"
    manifest["completed_at_utc"] = now()
    manifest["final_record"] = manifest["stages"]["06_final_answer"]
    write_json(manifest_path, manifest)
    return manifest
