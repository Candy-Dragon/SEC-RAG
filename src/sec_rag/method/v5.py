"""Compatibility imports for existing scripts; implementations live in responsibility modules."""
from sec_rag.method.constants import VERSION, PROMPT_ROOT, METHOD_CONFIG_PATH, LOADED_IMPLEMENTATION_PROVENANCE
from sec_rag.utils.stage_runtime import now, sha, write_json, concurrency_config, parallel_ordered
from sec_rag.llm.stage_call import response_record, prompt_path, StageValidationError, call_json
from sec_rag.retriever.bm25 import stage01_retrieval
from sec_rag.structurer.evidence import split_sentences, validate_grouping, stage02_evidence_units
from sec_rag.filter.integrity import validate_integrity, find_contiguous, stage03_integrity, validate_recovery
from sec_rag.filter.applicability import _clean_text_list, validate_information_needs, validate_evidence_mapping, load_source_chunk_context, applicability_evidence_input, stage04_applicability
from sec_rag.filter.coverage import validate_coverage, insufficient_coverage, stage05_coverage
from sec_rag.generator.constrained import validate_candidate, render_candidate_answer, fixed_insufficient_answer, stage06_generation
