from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from sec_rag.config import settings
from sec_rag.method.constants import VERSION
from sec_rag.llm.stage_call import call_json
from sec_rag.utils.stage_runtime import concurrency_config, now, parallel_ordered, sha, write_json


def _clean_text_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    result = [str(item).strip() for item in value]
    if any(not item for item in result):
        raise ValueError(f"{field} cannot contain empty text")
    return result


def validate_information_needs(value: Any, original_question: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"original_question", "information_needs", "context_spans"}:
        raise ValueError("Information-need output has missing or extra fields")
    if str(value["original_question"]).strip() != original_question:
        raise ValueError("The original question must be preserved exactly")
    needs = value["information_needs"]
    if not isinstance(needs, list) or not needs:
        raise ValueError("At least one explicit information need is required")
    clean_needs = []
    seen_spans: set[str] = set()
    for index, item in enumerate(needs, 1):
        if not isinstance(item, dict) or set(item) != {"need_id", "source_span", "description"}:
            raise ValueError("Every information need must contain need_id, source_span, and description")
        need_id = str(item["need_id"])
        span = str(item["source_span"]).strip()
        description = str(item["description"]).strip()
        if need_id != f"Q{index}" or not span or span not in original_question or not description:
            raise ValueError("Information needs must be consecutive and grounded in the original question")
        if span in seen_spans:
            raise ValueError("Information-need source spans cannot be duplicated")
        seen_spans.add(span)
        clean_needs.append({"need_id": need_id, "source_span": span, "description": description})
    contexts = _clean_text_list(value["context_spans"], "context_spans")
    if any(span not in original_question for span in contexts):
        raise ValueError("Every context span must occur verbatim in the original question")
    return {"original_question": original_question, "information_needs": clean_needs, "context_spans": contexts}


def validate_evidence_mapping(value: Any, evidence_id: str, allowed_need_ids: set[str]) -> dict[str, Any]:
    expected = {"evidence_id", "matched_need_ids", "supported_content", "required_conditions", "unsupported_extensions", "reason"}
    if not isinstance(value, dict) or set(value) != expected or str(value["evidence_id"]) != evidence_id:
        raise ValueError("Evidence mapping has missing fields or the wrong evidence ID")
    matched = [str(item) for item in value["matched_need_ids"]] if isinstance(value["matched_need_ids"], list) else []
    if len(matched) != len(set(matched)) or not set(matched) <= allowed_need_ids:
        raise ValueError("Evidence mapping cites an invalid or duplicate need ID")
    supported = _clean_text_list(value["supported_content"], "supported_content")
    conditions = _clean_text_list(value["required_conditions"], "required_conditions")
    unsupported = _clean_text_list(value["unsupported_extensions"], "unsupported_extensions")
    reason = str(value["reason"]).strip()
    if not reason or (bool(matched) != bool(supported)):
        raise ValueError("Matched evidence requires supported content; unmatched evidence must not invent it")
    return {"evidence_id": evidence_id, "matched_need_ids": matched, "supported_content": supported,
            "required_conditions": conditions, "unsupported_extensions": unsupported, "reason": reason}


def load_source_chunk_context(integrity_record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Recover each unit's original chunk so its omitted scope remains visible."""
    provenance = integrity_record.get("source_record") or {}
    relative = provenance.get("path")
    expected_hash = provenance.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected_hash, str):
        raise ValueError("Stage 03 lacks Stage 02 source provenance")
    stage02_path = (settings.root / relative).resolve()
    if not stage02_path.is_relative_to(settings.root.resolve()) or not stage02_path.exists() or sha(stage02_path) != expected_hash:
        raise ValueError("Stage 02 source provenance changed or is outside project root")
    stage02 = json.loads(stage02_path.read_text(encoding="utf-8"))
    if stage02.get("stage") != "02_evidence_units" or stage02.get("status") != "completed":
        raise ValueError("Stage 04 requires a completed Stage 02 source")
    if stage02.get("input") != integrity_record.get("input"):
        raise ValueError("Stage 02 and Stage 03 inputs do not match")
    chunks = stage02["candidate_chunks"]
    by_id = {str(chunk["chunk_id"]): chunk for chunk in chunks}
    if len(by_id) != len(chunks):
        raise ValueError("Duplicate source chunk IDs")
    return by_id


def applicability_evidence_input(unit: dict[str, Any], chunks_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    chunk = chunks_by_id.get(str(unit["source_chunk_id"]))
    if chunk is None:
        raise ValueError(f"Missing source chunk for {unit['evidence_id']}")
    source_ids = {sentence["sentence_id"] for sentence in chunk["sentences"]}
    if not set(unit["sentence_ids"]).issubset(source_ids):
        raise ValueError(f"Evidence sentence IDs not present in source chunk: {unit['evidence_id']}")
    return {
        "evidence_id": unit["evidence_id"], "source_file": unit["source_file"],
        "source_pages": unit["source_pages"], "section_heading": unit["section_heading"],
        "evidence_text": unit["evidence_text"], "source_chunk_id": unit["source_chunk_id"],
        "evidence_sentence_ids": unit["sentence_ids"],
        "source_chunk_sentences": chunk["sentences"],
        "context_policy": "Full chunk is only for recovering the evidence unit's scope; only evidence_text may be quoted as approved evidence.",
    }


def stage04_applicability(integrity_path: Path, output_path: Path) -> dict[str, Any]:
    source = json.loads(integrity_path.read_text(encoding="utf-8"))
    if source.get("stage") != "03_integrity" or source.get("status") != "completed":
        raise ValueError("Stage 04 requires completed stage 03")
    question = source["input"]["question"]
    chunks_by_id = load_source_chunk_context(source)
    workers = concurrency_config()["stage04_applicability_workers"]
    need_trace = call_json(
        "04_information_needs", "04_information_needs.txt",
        {"question_id": source["input"]["question_id"], "original_question": question},
        lambda value: validate_information_needs(value, question), max_tokens=1800,
    )
    need_annotation = need_trace["parsed_output"]
    allowed_need_ids = {item["need_id"] for item in need_annotation["information_needs"]}
    def assess_unit(unit: dict[str, Any]) -> dict[str, Any]:
        model_input = {
            "original_question": question,
            "information_needs": need_annotation["information_needs"],
            "context_spans": need_annotation["context_spans"],
            "evidence": applicability_evidence_input(unit, chunks_by_id),
        }
        trace = call_json(
            "04_applicability",
            "04_evidence_mapping_context.txt",
            model_input,
            lambda value, eid=unit["evidence_id"]: validate_evidence_mapping(value, eid, allowed_need_ids),
            max_tokens=2200,
        )
        mapping = trace["parsed_output"]
        return {"unit": unit, "mapping": mapping, "trace": trace}

    assessed_units = parallel_ordered(source["usable_evidence_units"], assess_unit, workers)
    mappings: list[dict[str, Any]] = []
    mapped: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    for assessed in assessed_units:
        unit, mapping, trace = assessed["unit"], assessed["mapping"], assessed["trace"]
        mappings.append(mapping)
        traces.append({"evidence_id": unit["evidence_id"], "trace": trace})
        enriched = {**unit, "need_mapping": mapping}
        (mapped if mapping["matched_need_ids"] else unmapped).append(enriched)
    record = {
        "created_at_utc": now(),
        "method_version": VERSION,
        "stage": "04_applicability",
        "status": "completed",
        "input": source["input"],
        "source_record": {"path": integrity_path.relative_to(settings.root).as_posix(), "sha256": sha(integrity_path)},
        "information_need_annotation": need_annotation,
        "information_need_model_trace": need_trace,
        "mapping_policy": "Map each evidence unit to fixed needs while preserving the scope in its original source chunk; context is not additional approved evidence.",
        "evidence_mappings": mappings,
        "mapping_model_traces": traces,
        "mapped_evidence_units": mapped,
        "unmapped_evidence_units": unmapped,
        "validation": {
            "valid": True,
            "input_count": len(source["usable_evidence_units"]),
            "information_need_count": len(need_annotation["information_needs"]),
            "mapping_count": len(mappings),
            "mapped_count": len(mapped),
            "unmapped_count": len(unmapped),
            "one_evidence_per_model_call": True,
            "parallel_workers": workers,
            "result_order": "evidence_id",
        },
    }
    write_json(output_path, record)
    return record
