from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from sec_rag.config import settings
from sec_rag.method.constants import LABELS, VERSION
from sec_rag.llm.stage_call import call_json
from sec_rag.utils.stage_runtime import concurrency_config, now, parallel_ordered, sha, write_json


def validate_integrity(value: Any, evidence_id: str) -> dict[str, Any]:
    if not isinstance(value, dict) or str(value.get("evidence_id")) != evidence_id or value.get("label") not in LABELS or not str(value.get("reason", "")).strip():
        raise ValueError("Invalid integrity result")
    return {"evidence_id": evidence_id, "label": value["label"], "reason": str(value["reason"]).strip()}


def find_contiguous(source: str, quote: str) -> str | None:
    compact_source = [(ch, i) for i, ch in enumerate(source) if not ch.isspace()]
    compact_quote = "".join(ch for ch in quote if not ch.isspace())
    if len(compact_quote) < 20:
        return None
    joined = "".join(ch for ch, _ in compact_source)
    at = joined.find(compact_quote)
    if at < 0:
        return None
    return source[compact_source[at][1]:compact_source[at + len(compact_quote) - 1][1] + 1]


def stage03_integrity(evidence_path: Path, output_path: Path) -> dict[str, Any]:
    source = json.loads(evidence_path.read_text(encoding="utf-8"))
    if source.get("stage") != "02_evidence_units" or source.get("status") != "completed":
        raise ValueError("Stage 03 requires completed stage 02")
    config = concurrency_config()
    integrity_workers = config["stage03_integrity_workers"]
    recovery_workers = config["stage03_recovery_workers"]
    def check_unit(unit: dict[str, Any]) -> dict[str, Any]:
        trace = call_json("03_integrity", "03_integrity.txt", unit, lambda value, eid=unit["evidence_id"]: validate_integrity(value, eid), max_tokens=1200)
        result = {**unit, "integrity": trace["parsed_output"]}
        return {"unit": result, "trace": trace}

    checks = parallel_ordered(source["evidence_units"], check_unit, integrity_workers)
    usable, withheld, recoveries = [], [], []
    for check in checks:
        result = check["unit"]
        if result["integrity"]["label"] == "complete":
            usable.append(result)
        else:
            withheld.append(result)

    def recover_unit(unit: dict[str, Any]) -> dict[str, Any]:
        trace = call_json("03_recover_quote", "03_recover_quote.txt", {"source_evidence_id": unit["evidence_id"], "evidence_text": unit["evidence_text"], "withheld_reason": unit["integrity"]["reason"]}, lambda value: validate_recovery(value, unit["evidence_id"]), max_tokens=1400)
        return {"unit": unit, "trace": trace, "recovery": trace["parsed_output"]}

    recovery_results = parallel_ordered(withheld, recover_unit, recovery_workers)
    for recovered_result in recovery_results:
        unit, trace = recovered_result["unit"], recovered_result["trace"]
        item = {"source_evidence_id": unit["evidence_id"], "trace": trace}
        recovery = recovered_result["recovery"]
        if recovery["recoverable"]:
            exact = find_contiguous(unit["evidence_text"], recovery["quote"])
            if exact is not None:
                recovered = {**unit, "evidence_id": f"E{len(source['evidence_units']) + len(recoveries) + 1:03d}", "evidence_text": exact, "recovered_from_evidence_id": unit["evidence_id"], "integrity": {"label": "complete", "reason": recovery["reason"], "recovery_policy": "exact_contiguous_source_span"}}
                usable.append(recovered); recoveries.append({**item, "accepted": True, "new_evidence_id": recovered["evidence_id"], "quote": exact}); continue
        recoveries.append({**item, "accepted": False})
    record = {"created_at_utc": now(), "method_version": VERSION, "stage": "03_integrity", "status": "completed", "input": source["input"], "source_record": {"path": evidence_path.relative_to(settings.root).as_posix(), "sha256": sha(evidence_path)}, "integrity_checks": checks, "usable_evidence_units": usable, "withheld_evidence_units": withheld, "quote_recovery": recoveries, "validation": {"valid": True, "usable_count": len(usable), "withheld_count": len(withheld), "integrity_parallel_workers": integrity_workers, "recovery_parallel_workers": recovery_workers, "result_order": "evidence_id"}}
    write_json(output_path, record)
    return record


def validate_recovery(value: Any, evidence_id: str) -> dict[str, Any]:
    if not isinstance(value, dict) or str(value.get("source_evidence_id")) != evidence_id or not isinstance(value.get("recoverable"), bool):
        raise ValueError("Invalid recovery result")
    quote, reason = str(value.get("quote", "")), str(value.get("reason", "")).strip()
    if value["recoverable"] and (not quote or not reason):
        raise ValueError("Recoverable result needs quote and reason")
    if not value["recoverable"] and quote:
        raise ValueError("Non-recoverable result must have an empty quote")
    return {"source_evidence_id": evidence_id, "recoverable": value["recoverable"], "quote": quote, "reason": reason}
