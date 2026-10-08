"""Shared serialization and validation for the active metrics only."""
from pathlib import Path
from typing import Any
import json
from sec_rag.config import settings
ROOT = settings.root
PILOT = ROOT / "storage/experiments/testing/pilot/sec-rag-v5/evidence_alignment_top5"
PROMPTS = ROOT / "configs/prompts/evaluation"

def check_prompts() -> None:
    for name in ("00_classify_units.txt", "01_extract_statements.txt",
                 "01_claim_entailment.txt", "02_citation_sentence_support.txt"):
        path = PROMPTS / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            raise ValueError(f"Required evaluation prompt missing or empty: {path}")

def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def validate_binary_list(value: Any, key: str, ids: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get(key), list): raise ValueError(f"missing {key}")
    rows = value[key]
    if [str(x.get("id", "")) for x in rows] != ids: raise ValueError(f"{key} IDs/order mismatch")
    for row in rows:
        if not isinstance(row.get("label"), bool) or not str(row.get("reason", "")).strip(): raise ValueError("invalid label/reason")
    return value

def validate_citation_set_support(value: Any) -> dict[str, Any]:
    if not isinstance(value,dict) or not isinstance(value.get("supported"),bool) or not str(value.get("reason","")).strip():
        raise ValueError("invalid citation set support result")
    return {"supported":value["supported"],"reason":str(value["reason"]).strip()}
