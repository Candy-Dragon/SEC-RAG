"""Optional deterministic sentence units for interface checks/ablation, not the default method."""
import json
from sec_rag.config import settings
from sec_rag.method.constants import VERSION
from sec_rag.structurer.evidence import split_sentences
from sec_rag.utils.stage_runtime import now, sha, write_json


def stage02_sentences(input_path, output_path):
    source = json.loads(input_path.read_text(encoding="utf-8"))
    chunks = split_sentences(source["retrieval_results"])
    units = []
    for chunk in chunks:
        for sentence in chunk["sentences"]:
            units.append({
                "evidence_id": f"E{len(units) + 1:03d}", "source_chunk_id": chunk["chunk_id"],
                "source_rank": chunk["rank"], "source_document_id": chunk["document_id"],
                "source_file": chunk["source_file"], "source_pages": [chunk["page_start"], chunk["page_end"]],
                "section_heading": chunk["section_heading"], "sentence_ids": [sentence["sentence_id"]],
                "evidence_text": sentence["text"],
            })
    record = {
        "created_at_utc": now(), "method_version": VERSION, "stage": "02_evidence_units", "status": "completed",
        "input": source["input"], "source_record": {"path": input_path.relative_to(settings.root).as_posix(), "sha256": sha(input_path)},
        "candidate_chunks": chunks, "evidence_units": units, "excluded_sentences": [], "chunk_model_traces": [],
        "validation": {"valid": True, "model_call_skipped": True, "policy": "one_source_sentence_per_unit"},
    }
    write_json(output_path, record)
    return record
