from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from sec_rag.config import settings
from sec_rag.method.constants import VERSION
from sec_rag.llm.stage_call import call_json
from sec_rag.utils.stage_runtime import now, sha, write_json


def validate_candidate(value: Any, allowed_ids: set[str], required_insufficient: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"answer", "claims", "insufficient_information"}:
        raise ValueError("Generation output has missing or extra fields")
    answer = str(value["answer"]).strip()
    claims = value["claims"]
    insufficient = value["insufficient_information"]
    if not answer or not isinstance(claims, list) or not isinstance(insufficient, list):
        raise ValueError("Answer and both output lists are required")
    clean_claims = []
    for index, claim in enumerate(claims, 1):
        if not isinstance(claim, dict) or str(claim.get("claim_id")) != f"C{index}":
            raise ValueError("Claim IDs must be consecutive")
        text = str(claim.get("text", "")).strip()
        ids = claim.get("evidence_ids")
        claim_type = claim.get("claim_type")
        if not text or not isinstance(ids, list) or not ids or claim_type not in {"fact", "condition", "recommendation", "safety_boundary"}:
            raise ValueError(f"Invalid claim C{index}")
        ids = [str(eid) for eid in ids]
        if len(ids) != len(set(ids)) or not set(ids) <= allowed_ids:
            raise ValueError(f"Claim C{index} cites invalid evidence")
        clean_claims.append({"claim_id": f"C{index}", "text": text, "evidence_ids": ids, "claim_type": claim_type})
    clean_insufficient = []
    returned_need_ids: set[str] = set()
    for item in insufficient:
        if not isinstance(item, dict):
            raise ValueError("Insufficient item must be an object")
        need_id = str(item.get("need_id", ""))
        statement = str(item.get("statement", "")).strip()
        if not need_id or not statement or need_id in returned_need_ids:
            raise ValueError("Invalid or duplicate insufficient item")
        returned_need_ids.add(need_id)
        clean_insufficient.append({"need_id": need_id, "statement": statement})
    if not required_insufficient <= returned_need_ids:
        raise ValueError("Required insufficient-information needs were omitted")
    # Each claim is one model-written answer sentence. Rebuild the displayed
    # answer from those sentences so every medical sentence carries its own
    # approved evidence citation. This is a format/provenance check, not a
    # post-generation semantic verifier.
    canonical_answer = render_candidate_answer(clean_claims, clean_insufficient)
    return {
        "answer": canonical_answer,
        "claims": clean_claims,
        "insufficient_information": clean_insufficient,
        "model_answer_matched_structured_sentences": answer == canonical_answer,
    }


def render_candidate_answer(
    claims: list[dict[str, Any]],
    insufficient_information: list[dict[str, Any]],
) -> str:
    """Render the final answer from model-written, citation-bearing sentences."""
    sections = [
        claim["text"] + " " + "".join(f"[{eid}]" for eid in claim["evidence_ids"])
        for claim in claims
    ]
    sections.extend(item["statement"] for item in insufficient_information)
    return "\n\n".join(sections).strip()


def fixed_insufficient_answer() -> str:
    return "当前检索及筛选没有获得足以回答该问题的适用指南证据，无法基于当前证据提供具体结论。"


def stage06_generation(coverage_path: Path, output_path: Path) -> dict[str, Any]:
    source = json.loads(coverage_path.read_text(encoding="utf-8"))
    if source.get("stage") != "05_coverage" or source.get("status") != "completed":
        raise ValueError("Stage 06 requires completed stage 05")
    analysis = source["coverage_analysis"]
    allowed_ids = set(analysis["generation_boundaries"]["allowed_evidence_ids"])
    units = [unit for unit in source["mapped_evidence_units"] if unit["evidence_id"] in allowed_ids]
    should_generate = analysis["overall_coverage"] != "none" and bool(units)
    if should_generate:
        model_input = {
            "question": source["input"]["question"],
            "approved_evidence": [{
                "evidence_id": unit["evidence_id"], "source_file": unit["source_file"],
                "source_pages": unit["source_pages"], "section_heading": unit["section_heading"],
                "evidence_text": unit["evidence_text"],
            } for unit in units],
            "information_need_annotation": source["information_need_annotation"],
            "coverage_analysis": analysis,
        }
        allowed = allowed_ids
        required = set(analysis["generation_boundaries"]["must_state_insufficient_need_ids"])
        trace = call_json("06_final_answer", "06_generation.txt", model_input, lambda value: validate_candidate(value, allowed, required), max_tokens=5000)
        candidate = trace["parsed_output"]
    else:
        trace = None
        candidate = {"answer": fixed_insufficient_answer(), "claims": [], "insufficient_information": [{"need_id": item["need_id"], "statement": "当前适用指南证据不足。"} for item in analysis["coverage_items"]]}
    record = {
        "created_at_utc": now(), "method_version": VERSION, "stage": "06_final_answer", "status": "completed",
        "input": source["input"], "source_record": {"path": coverage_path.relative_to(settings.root).as_posix(), "sha256": sha(coverage_path)},
        "approved_evidence": units, "coverage_analysis": analysis, "model_trace": trace,
        "final_answer": candidate,
        "validation": {
            "valid": True,
            "model_call_skipped": not should_generate,
            "generation_uses_original_approved_evidence": True,
            "every_medical_sentence_has_approved_citation": True,
            "post_generation_semantic_verification_used": False,
        },
    }
    write_json(output_path, record)
    return record
