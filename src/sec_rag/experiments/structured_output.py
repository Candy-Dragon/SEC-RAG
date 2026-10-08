"""Parse and validate the common model-output schema."""

from __future__ import annotations

import json
import re
from typing import Any

from sec_rag.llm.deepseek_client import DeepSeekAPIError


REQUIRED_FIELDS = {
    "answer",
    "citations",
    "evidence_sufficient",
    "insufficiency_reason",
}


def parse_common_output(
    content: str,
    *,
    evidence_count: int,
    expected_sufficiency: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise DeepSeekAPIError(f"Method returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise DeepSeekAPIError("Method output must be a JSON object.")
    missing = sorted(REQUIRED_FIELDS - set(parsed))
    if missing:
        raise DeepSeekAPIError(f"Method JSON missing fields: {missing}")
    if not isinstance(parsed["answer"], str):
        raise DeepSeekAPIError("answer must be a string.")
    if not isinstance(parsed["citations"], list):
        raise DeepSeekAPIError("citations must be a list.")
    normalized_citations: list[int] = []
    for value in parsed["citations"]:
        if isinstance(value, bool):
            raise DeepSeekAPIError("Citation must be an evidence number, not a boolean.")
        if isinstance(value, int):
            number = value
        elif isinstance(value, str) and (match := re.fullmatch(r"(?:\[证据([1-9]\d*)\]|证据([1-9]\d*))", value)):
            number = int(match.group(1) or match.group(2))
        else:
            raise DeepSeekAPIError("Citation must be an integer or a '证据N'/'[证据N]' marker.")
        if not 1 <= number <= evidence_count:
            raise DeepSeekAPIError("Output contains a citation outside the supplied evidence range.")
        normalized_citations.append(number)
    parsed["citations"] = normalized_citations
    sufficiency = parsed["evidence_sufficient"]
    if expected_sufficiency == "null" and sufficiency is not None:
        raise DeepSeekAPIError("evidence_sufficient must be null for this method.")
    if expected_sufficiency == "boolean" and not isinstance(sufficiency, bool):
        raise DeepSeekAPIError("evidence_sufficient must be boolean for this method.")
    if not isinstance(parsed["insufficiency_reason"], str):
        raise DeepSeekAPIError("insufficiency_reason must be a string.")
    validation = {
        "json_valid": True,
        "common_fields_present": True,
        "citation_numbers_valid": True,
        "evidence_count": evidence_count,
        "sufficiency_type_valid": True,
    }
    return parsed, validation
