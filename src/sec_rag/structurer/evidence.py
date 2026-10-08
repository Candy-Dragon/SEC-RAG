from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from sec_rag.config import settings
from sec_rag.method.constants import SENTENCE_BOUNDARY, VERSION
from sec_rag.llm.stage_call import call_json
from sec_rag.utils.stage_runtime import concurrency_config, now, parallel_ordered, sha, write_json


def split_sentences(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks = []
    for position, result in enumerate(results, 1):
        parts = [part.strip() for part in SENTENCE_BOUNDARY.split(str(result["text"])) if part.strip()]
        if not parts:
            raise ValueError(f"Chunk {result['chunk_id']} has no sentences")
        chunks.append({
            "rank": result["rank"], "chunk_id": result["chunk_id"], "document_id": result["document_id"],
            "source_file": result["source_file"], "page_start": result["page_start"], "page_end": result["page_end"],
            "section_heading": result.get("section_heading", ""),
            "sentences": [{"sentence_id": f"C{position}S{i}", "text": text} for i, text in enumerate(parts, 1)],
        })
    return chunks


def validate_grouping(value: Any, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"chunk_id", "evidence_groups", "excluded_sentences"}:
        raise ValueError("Grouping output must contain chunk_id, evidence_groups, excluded_sentences")
    chunk_id = str(value["chunk_id"])
    if len(chunks) != 1 or chunk_id != chunks[0]["chunk_id"]:
        raise ValueError("Grouping output must refer to the requested chunk")
    source = chunks[0]
    sentence_map = {x["sentence_id"]: x["text"] for x in source["sentences"]}
    order = {x["sentence_id"]: i for i, x in enumerate(source["sentences"])}
    groups = value["evidence_groups"]
    excluded = value["excluded_sentences"]
    if not isinstance(groups, list) or not isinstance(excluded, list):
        raise ValueError("Evidence groups and exclusions must be lists")
    used: list[str] = []
    normalized_groups = []
    for group in groups:
        ids = group.get("sentence_ids") if isinstance(group, dict) else None
        if not isinstance(ids, list) or not ids:
            raise ValueError("Evidence group must contain sentence IDs")
        ids = [str(x) for x in ids]
        if any(x not in sentence_map for x in ids):
            raise ValueError("Evidence group contains unknown sentence ID")
        positions = [order[x] for x in ids]
        if positions != list(range(positions[0], positions[0] + len(positions))):
            raise ValueError("Evidence group must be adjacent and ordered")
        used.extend(ids)
        normalized_groups.append({"sentence_ids": ids})
    normalized_excluded = []
    for item in excluded:
        if not isinstance(item, dict):
            raise ValueError("Excluded sentence must be an object")
        sid, reason = str(item.get("sentence_id", "")), str(item.get("reason", "")).strip()
        if sid not in sentence_map or not reason:
            raise ValueError("Excluded sentence ID or reason is invalid")
        used.append(sid)
        normalized_excluded.append({"sentence_id": sid, "reason": reason})
    expected = list(sentence_map)
    if len(used) != len(set(used)) or set(used) != set(expected):
        raise ValueError("Every sentence must be assigned exactly once")
    return {"chunk_id": chunk_id, "evidence_groups": normalized_groups, "excluded_sentences": normalized_excluded}


def stage02_evidence_units(retrieval_path: Path, output_path: Path) -> dict[str, Any]:
    retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
    if retrieval.get("stage") != "01_retrieval" or retrieval.get("status") != "completed":
        raise ValueError("Stage 02 requires completed stage 01")
    chunks = split_sentences(retrieval["retrieval_results"])
    workers = concurrency_config()["stage02_chunk_workers"]
    def process_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
        model_input = {"chunk_id": chunk["chunk_id"], "sentences": chunk["sentences"]}
        trace = call_json("02_evidence_units", "02_evidence_units.txt", model_input, lambda value, c=[chunk]: validate_grouping(value, c), max_tokens=2500)
        return {"chunk": chunk, "trace": trace, "parsed": trace["parsed_output"]}

    processed_chunks = parallel_ordered(chunks, process_chunk, workers)
    traces = []
    units = []
    exclusions = []
    number = 0
    for processed in processed_chunks:
        chunk, trace, parsed = processed["chunk"], processed["trace"], processed["parsed"]
        sentence_map = {x["sentence_id"]: x["text"] for x in chunk["sentences"]}
        for group in parsed["evidence_groups"]:
            number += 1
            units.append({
                "evidence_id": f"E{number:03d}", "source_chunk_id": chunk["chunk_id"], "source_rank": chunk["rank"],
                "source_document_id": chunk["document_id"], "source_file": chunk["source_file"], "source_pages": [chunk["page_start"], chunk["page_end"]],
                "section_heading": chunk["section_heading"], "sentence_ids": group["sentence_ids"],
                "evidence_text": "".join(sentence_map[sid] for sid in group["sentence_ids"]),
            })
        exclusions.extend([{**item, "source_chunk_id": chunk["chunk_id"], "text": sentence_map[item["sentence_id"]]} for item in parsed["excluded_sentences"]])
        traces.append(trace)
    record = {
        "created_at_utc": now(), "method_version": VERSION, "stage": "02_evidence_units", "status": "completed",
        "input": retrieval["input"], "source_record": {"path": retrieval_path.relative_to(settings.root).as_posix(), "sha256": sha(retrieval_path)},
        "candidate_chunks": chunks, "chunk_model_traces": traces, "evidence_units": units, "excluded_sentences": exclusions,
        "validation": {"valid": True, "evidence_unit_count": len(units), "excluded_sentence_count": len(exclusions), "source_sentence_assignment": "exactly_once", "parallel_workers": workers, "result_order": "source_chunk_rank"},
    }
    write_json(output_path, record)
    return record
