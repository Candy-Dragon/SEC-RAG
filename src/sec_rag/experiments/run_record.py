"""Create and persist one complete experiment run record."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sec_rag.config import settings
from sec_rag.llm.types import ChatMessage, ModelResponse
from sec_rag.paths import ensure_parent_dir


class BaselineOutputValidationError(RuntimeError):
    """A model response failed validation; its full run record remains available."""

    def __init__(self, message: str, record: dict[str, Any]) -> None:
        super().__init__(message)
        self.record = record


def create_run_record(
    *,
    method: str,
    question: str,
    messages: list[ChatMessage],
    response: ModelResponse,
    retrieval: list[dict[str, Any]] | None = None,
    answer_override: str | None = None,
    method_output: dict[str, Any] | None = None,
    prompt_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc)
    return {
        "run_id": f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}",
        "created_at_utc": timestamp.isoformat(),
        "method": method,
        "question": question,
        "messages": [message.as_dict() for message in messages],
        "prompt_info": prompt_info or {},
        "retrieval": retrieval or [],
        "answer": response.content if answer_override is None else answer_override,
        "method_output": method_output or {},
        "model": {
            "requested_model": response.requested_model,
            "returned_model": response.returned_model,
            "request_id": response.request_id,
            "finish_reason": response.finish_reason,
            "attempt_count": response.attempt_count,
            "latency_seconds": response.latency_seconds,
            "usage": asdict(response.usage),
        },
        "raw_model_response": response.raw_response,
    }


def write_run_record(
    record: dict[str, Any],
    *,
    result_scope: str = "testing/single_question/common_output_v1",
) -> Path:
    """Write a run under an explicit test/formal scope.

    Single-question entry scripts use the default testing scope. A future
    batch runner must pass its own formal batch scope explicitly.
    """
    method = str(record["method"])
    path = ensure_parent_dir(
        settings.storage_path
        / "experiments"
        / result_scope
        / method
        / f"{record['run_id']}.json"
    )
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
