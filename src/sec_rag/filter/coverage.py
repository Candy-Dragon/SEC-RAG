from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from sec_rag.config import settings
from sec_rag.method.constants import COVERAGE_LABELS, VERSION
from sec_rag.filter.applicability import _clean_text_list
from sec_rag.llm.stage_call import call_json
from sec_rag.utils.stage_runtime import now, sha, write_json


def validate_coverage(
    value: Any,
    information_needs: list[dict[str, Any]],
    mapped_ids_by_need: dict[str, set[str]],
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"coverage_items"}:
        raise ValueError("Coverage output must contain only coverage_items")
    items = value["coverage_items"]
    if not isinstance(items, list) or len(items) != len(information_needs):
        raise ValueError("Coverage must contain exactly one item for every fixed information need")
    clean_items: list[dict[str, Any]] = []
    for expected_need, item in zip(information_needs, items):
        expected_keys = {"need_id", "source_span", "coverage", "evidence_usage", "supported_scope", "missing_scope", "required_conditions", "forbidden_content", "reason"}
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise ValueError("Coverage item has missing or extra fields")
        need_id = str(item["need_id"])
        source_span = str(item["source_span"]).strip()
        coverage = item.get("coverage")
        reason = str(item["reason"]).strip()
        if need_id != expected_need["need_id"] or source_span != expected_need["source_span"] or coverage not in COVERAGE_LABELS or not reason:
            raise ValueError("Stage 05 must preserve the fixed need IDs and source spans")
        usage = item["evidence_usage"]
        if not isinstance(usage, list):
            raise ValueError("evidence_usage must be a list")
        clean_usage = []
        seen_evidence: set[str] = set()
        for entry in usage:
            expected_usage = {"evidence_id", "supported_content", "required_conditions", "used_for_generation", "reason"}
            if not isinstance(entry, dict) or set(entry) != expected_usage:
                raise ValueError("Evidence usage has missing or extra fields")
            eid = str(entry["evidence_id"])
            if eid in seen_evidence or eid not in mapped_ids_by_need.get(need_id, set()):
                raise ValueError(f"Coverage item {need_id} uses evidence not mapped to this need")
            seen_evidence.add(eid)
            supported = str(entry["supported_content"]).strip()
            usage_reason = str(entry["reason"]).strip()
            if not supported or not usage_reason or not isinstance(entry["used_for_generation"], bool):
                raise ValueError("Evidence usage content, flag, or reason is invalid")
            clean_usage.append({"evidence_id": eid, "supported_content": supported,
                                "required_conditions": _clean_text_list(entry["required_conditions"], "required_conditions"),
                                "used_for_generation": entry["used_for_generation"], "reason": usage_reason})
        if seen_evidence != mapped_ids_by_need.get(need_id, set()):
            raise ValueError(f"Coverage item {need_id} must account for every evidence unit mapped to it")
        used_ids = [entry["evidence_id"] for entry in clean_usage if entry["used_for_generation"]]
        if coverage in {"full", "partial"} and not used_ids:
            raise ValueError(f"{coverage} coverage requires at least one evidence unit approved for generation")
        if coverage == "none" and used_ids:
            raise ValueError("none coverage cannot approve evidence for generation")
        supported_scope = _clean_text_list(item["supported_scope"], "supported_scope")
        missing_scope = _clean_text_list(item["missing_scope"], "missing_scope")
        if coverage == "full" and (not supported_scope or missing_scope):
            raise ValueError("full coverage requires supported scope and no missing scope")
        if coverage == "partial" and (not supported_scope or not missing_scope):
            raise ValueError("partial coverage requires both supported and missing scope")
        if coverage == "none" and supported_scope:
            raise ValueError("none coverage cannot contain supported scope")
        clean_items.append({
            "need_id": need_id, "source_span": source_span, "coverage": coverage,
            "evidence_usage": clean_usage, "supported_scope": supported_scope, "missing_scope": missing_scope,
            "required_conditions": _clean_text_list(item["required_conditions"], "required_conditions"),
            "forbidden_content": _clean_text_list(item["forbidden_content"], "forbidden_content"), "reason": reason,
        })
    must_answer = [item["need_id"] for item in clean_items if item["coverage"] in {"full", "partial"}]
    must_insufficient = [item["need_id"] for item in clean_items if item["coverage"] in {"partial", "none"}]
    allowed_ids = list(dict.fromkeys(entry["evidence_id"] for item in clean_items for entry in item["evidence_usage"] if entry["used_for_generation"]))
    conditions = list(dict.fromkeys(text for item in clean_items for text in item["required_conditions"]))
    forbidden = list(dict.fromkeys(text for item in clean_items for text in item["forbidden_content"]))
    overall = "full" if all(item["coverage"] == "full" for item in clean_items) else "partial" if must_answer else "none"
    return {
        "coverage_items": clean_items,
        "generation_boundaries": {
            "must_answer_need_ids": must_answer,
            "must_state_insufficient_need_ids": must_insufficient,
            "allowed_evidence_ids": allowed_ids, "must_preserve_conditions": conditions, "forbidden_content": forbidden,
        },
        "overall_coverage": overall,
        "overall_coverage_derivation": "program_rule_from_coverage_items",
    }


def insufficient_coverage(reason: str, information_needs: list[dict[str, Any]]) -> dict[str, Any]:
    items = [{"need_id": need["need_id"], "source_span": need["source_span"], "coverage": "none",
              "evidence_usage": [], "supported_scope": [], "missing_scope": ["当前证据不能支持该信息需求"],
              "required_conditions": [], "forbidden_content": ["当前证据未支持的医学结论或建议"], "reason": reason}
             for need in information_needs]
    return {"coverage_items": items,
            "generation_boundaries": {"must_answer_need_ids": [],
                "must_state_insufficient_need_ids": [item["need_id"] for item in items],
                "allowed_evidence_ids": [], "must_preserve_conditions": [],
                "forbidden_content": ["当前证据未支持的医学结论或建议"]},
            "overall_coverage": "none", "overall_coverage_derivation": "program_rule_no_mapped_evidence"}


def stage05_coverage(applicability_path: Path, output_path: Path) -> dict[str, Any]:
    source = json.loads(applicability_path.read_text(encoding="utf-8"))
    if source.get("stage") != "04_applicability" or source.get("status") != "completed":
        raise ValueError("Stage 05 requires completed stage 04")
    annotation = source["information_need_annotation"]
    needs = annotation["information_needs"]
    units = source["mapped_evidence_units"]
    grouped_ids = {
        need["need_id"]: [unit["evidence_id"] for unit in units if need["need_id"] in unit["need_mapping"]["matched_need_ids"]]
        for need in needs
    }
    if units:
        model_input = {
            "original_question": source["input"]["question"],
            "information_needs": needs,
            "evidence_grouping": grouped_ids,
            "mapped_evidence": [{
                "evidence_id": unit["evidence_id"],
                "source_file": unit["source_file"],
                "source_pages": unit["source_pages"],
                "section_heading": unit["section_heading"],
                "evidence_text": unit["evidence_text"],
                "need_mapping": unit["need_mapping"],
            } for unit in units],
        }
        mapped_sets = {need_id: set(ids) for need_id, ids in grouped_ids.items()}
        trace = call_json("05_coverage", "05_coverage.txt", model_input, lambda value: validate_coverage(value, needs, mapped_sets), max_tokens=5000)
        analysis = trace["parsed_output"]
    else:
        trace = None
        analysis = insufficient_coverage(
            "No complete evidence unit was mapped to any fixed information need.", needs,
        )
    record = {
        "created_at_utc": now(), "method_version": VERSION, "stage": "05_coverage", "status": "completed",
        "input": source["input"],
        "source_record": {"path": applicability_path.relative_to(settings.root).as_posix(), "sha256": sha(applicability_path)},
        "information_need_annotation": annotation,
        "evidence_grouping": grouped_ids,
        "mapped_evidence_units": units,
        "model_trace": trace,
        "coverage_analysis": analysis,
        "validation": {"valid": True, "model_call_skipped": not bool(units), "coverage_is_not_final_answer": True},
    }
    write_json(output_path, record)
    return record
