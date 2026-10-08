"""Stage selection and structural contracts. This is not a semantic evaluator."""
from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path

from sec_rag.config import settings
from sec_rag.utils.stage_runtime import sha, write_json

DEFAULTS = {
    "01_retrieval": "sec_rag.retriever.bm25:stage01_retrieval",
    "02_evidence_units": "sec_rag.structurer.evidence:stage02_evidence_units",
    "03_integrity": "sec_rag.filter.integrity:stage03_integrity",
    "04_applicability": "sec_rag.filter.applicability:stage04_applicability",
    "05_coverage": "sec_rag.filter.coverage:stage05_coverage",
    "06_final_answer": "sec_rag.generator.constrained:stage06_generation",
}
FIELDS = {
    "01_retrieval": {"retrieval_results": list},
    "02_evidence_units": {"candidate_chunks": list, "evidence_units": list, "excluded_sentences": list},
    "03_integrity": {"usable_evidence_units": list, "withheld_evidence_units": list},
    "04_applicability": {"information_need_annotation": dict, "mapped_evidence_units": list},
    "05_coverage": {"information_need_annotation": dict, "mapped_evidence_units": list, "coverage_analysis": dict},
    "06_final_answer": {"approved_evidence": list, "coverage_analysis": dict, "final_answer": dict},
}


def resolve_components(overrides=None):
    overrides = {} if overrides is None else overrides
    if not isinstance(overrides, dict) or set(overrides) - set(DEFAULTS):
        raise ValueError("components must map existing stage names to module:function")
    result = {}
    for stage, target in (DEFAULTS | overrides).items():
        if not isinstance(target, str) or target.count(":") != 1:
            raise ValueError(f"Invalid component target: {stage}")
        module, name = target.split(":")
        function = getattr(importlib.import_module(module), name)
        if not callable(function):
            raise ValueError(f"Component is not callable: {target}")
        if stage == "01_retrieval":
            inspect.signature(function).bind("question", question_id="id", source_dataset="dataset",
                                             disease_scope="scope", top_n=5, output_path=Path("output.json"))
        else:
            inspect.signature(function).bind(Path("input.json"), Path("output.json"))
        source = Path(inspect.getsourcefile(function)).resolve()
        if not source.is_relative_to(settings.root.resolve()):
            raise ValueError("Component source must be inside the checkout for reproducibility")
        result[stage] = (function, {"target": target, "path": source.relative_to(settings.root).as_posix(), "sha256": sha(source)})
    return result


def validate_record(record, stage, expected_input):
    if not isinstance(record, dict) or record.get("status") != "completed" or record.get("stage") != stage:
        raise ValueError(f"{stage}: expected a completed stage record")
    if record.get("input") != expected_input:
        raise ValueError(f"{stage}: original question/input changed")
    for field, kind in FIELDS[stage].items():
        if not isinstance(record.get(field), kind):
            raise ValueError(f"{stage}: missing/invalid {field}")
    if stage == "01_retrieval":
        rows = record["retrieval_results"]
        if len(rows) != expected_input["top_n"]:
            raise ValueError("Retrieval count must match top_n")
        ids = []
        for rank, row in enumerate(rows, 1):
            for key in ("chunk_id", "document_id", "source_file", "page_start", "page_end", "text", "rank", "disease"):
                if key not in row:
                    raise ValueError(f"Retrieval missing {key}")
            if row["rank"] != rank or row["disease"] != expected_input["disease_scope"] or not row["text"].strip():
                raise ValueError("Invalid retrieval rank/scope/text")
            ids.append(row["chunk_id"])
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate retrieval IDs")
    for field in ("evidence_units", "usable_evidence_units", "mapped_evidence_units", "approved_evidence"):
        if field not in record:
            continue
        ids = []
        for unit in record[field]:
            for key in ("evidence_id", "evidence_text", "source_chunk_id", "source_file", "source_pages", "sentence_ids", "section_heading"):
                if key not in unit:
                    raise ValueError(f"{stage}: evidence missing {key}")
            ids.append(unit["evidence_id"])
        if len(set(ids)) != len(ids):
            raise ValueError(f"{stage}: duplicate evidence IDs")
    if "information_need_annotation" in record:
        annotation = record["information_need_annotation"]
        if annotation.get("original_question") != expected_input["question"] or not isinstance(annotation.get("information_needs"), list):
            raise ValueError("Information needs must preserve the original question")
    if "coverage_analysis" in record:
        analysis = record["coverage_analysis"]
        if analysis.get("overall_coverage") not in {"full", "partial", "none"} or not isinstance(analysis.get("generation_boundaries"), dict):
            raise ValueError("Invalid coverage analysis")
    if stage == "06_final_answer":
        answer = record["final_answer"]
        if not isinstance(answer.get("answer"), str) or not answer["answer"].strip() or not isinstance(answer.get("claims"), list) or not isinstance(answer.get("insufficient_information"), list):
            raise ValueError("Invalid final answer")


def execute(stage, resolved, input_record, output_path, source_path=None):
    function, provenance = resolved[stage]
    if stage == "01_retrieval":
        question = input_record["question"]
        record = function(question, **{k: v for k, v in input_record.items() if k != "question"}, output_path=output_path)
    else:
        record = function(source_path, output_path)
    validate_record(record, stage, input_record)
    validate_links(record, stage, source_path)
    record["component"] = provenance
    if source_path is not None:
        record["source_record"] = {"path": source_path.relative_to(settings.root).as_posix(), "sha256": sha(source_path)}
    write_json(output_path, record)
    return record


def validate_links(record, stage, source_path):
    """Check the provenance/ID contracts required by downstream built-in stages."""
    if stage == "01_retrieval":
        return
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if stage == "02_evidence_units":
        originals = {x["chunk_id"] for x in source["retrieval_results"]}
        chunks = record["candidate_chunks"]
        by_id = {x["chunk_id"]: x for x in chunks}
        if len(by_id) != len(chunks) or set(by_id) != originals:
            raise ValueError("candidate_chunks must preserve the retrieved chunk IDs")
        for chunk in chunks:
            sentences = chunk["sentences"]
            ids = [x["sentence_id"] for x in sentences]
            if len(set(ids)) != len(ids) or any(not isinstance(x["text"], str) or not x["text"].strip() for x in sentences):
                raise ValueError("Invalid source sentence IDs/text")
        for unit in record["evidence_units"]:
            chunk = by_id[unit["source_chunk_id"]]
            if not unit["sentence_ids"] or not set(unit["sentence_ids"]) <= {x["sentence_id"] for x in chunk["sentences"]}:
                raise ValueError("Evidence refers to unknown source sentences")
    if stage == "03_integrity":
        originals = {x["evidence_id"]: x for x in source["evidence_units"]}
        for unit in record["usable_evidence_units"]:
            original = originals[unit.get("recovered_from_evidence_id", unit["evidence_id"])]
            if unit["source_chunk_id"] != original["source_chunk_id"] or unit["sentence_ids"] != original["sentence_ids"]:
                raise ValueError("Integrity stage changed evidence provenance")
    if stage in {"04_applicability", "05_coverage"}:
        needs = record["information_need_annotation"]["information_needs"]
        nids = [x["need_id"] for x in needs]
        if not nids or len(set(nids)) != len(nids):
            raise ValueError("Information need IDs must be nonempty and unique")
        original_question = record["input"]["question"]
        if any(not x["source_span"] or x["source_span"] not in original_question for x in needs):
            raise ValueError("Information needs must quote the original question")
        previous_field = "usable_evidence_units" if stage == "04_applicability" else "mapped_evidence_units"
        previous = {x["evidence_id"]: x for x in source[previous_field]}
        for unit in record["mapped_evidence_units"]:
            original = previous[unit["evidence_id"]]
            if unit["evidence_text"] != original["evidence_text"] or unit["source_chunk_id"] != original["source_chunk_id"]:
                raise ValueError("Mapping/coverage changed evidence text or origin")
            if not set(unit["need_mapping"]["matched_need_ids"]) <= set(nids):
                raise ValueError("Evidence maps to unknown needs")
    if stage == "05_coverage":
        if record["information_need_annotation"] != source["information_need_annotation"]:
            raise ValueError("Coverage must preserve the annotated needs")
        bounds = record["coverage_analysis"]["generation_boundaries"]
        known = {x["evidence_id"] for x in record["mapped_evidence_units"]}
        if not set(bounds["allowed_evidence_ids"]) <= known:
            raise ValueError("Coverage permits unknown evidence")
        for key in ("must_answer_need_ids", "must_state_insufficient_need_ids"):
            if not set(bounds[key]) <= set(nids):
                raise ValueError("Coverage refers to unknown needs")
        if {x["need_id"] for x in record["coverage_analysis"]["coverage_items"]} != set(nids):
            raise ValueError("Coverage must account for every need")
    if stage == "06_final_answer":
        allowed = set(source["coverage_analysis"]["generation_boundaries"]["allowed_evidence_ids"])
        approved = {x["evidence_id"] for x in record["approved_evidence"]}
        if not approved <= allowed or record["coverage_analysis"] != source["coverage_analysis"]:
            raise ValueError("Generation changed the approved evidence boundary")
        for claim in record["final_answer"]["claims"]:
            if not claim["evidence_ids"] or not set(claim["evidence_ids"]) <= approved:
                raise ValueError("Final claim has missing/unknown citations")
