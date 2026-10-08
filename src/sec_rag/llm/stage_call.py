from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable
from sec_rag.config import settings
from sec_rag.llm.deepseek_client import DeepSeekClient
from sec_rag.llm.types import ChatMessage, ModelResponse
from sec_rag.method.constants import PROMPT_ROOT
from sec_rag.utils.stage_runtime import sha


def response_record(response: ModelResponse) -> dict[str, Any]:
    return {
        "request_id": response.request_id,
        "requested_model": response.requested_model,
        "returned_model": response.returned_model,
        "finish_reason": response.finish_reason,
        "attempt_count": response.attempt_count,
        "latency_seconds": response.latency_seconds,
        "usage": asdict(response.usage),
        "content": response.content,
        "reasoning_content": response.reasoning_content,
        "raw_response": response.raw_response,
    }


def prompt_path(filename: str) -> Path:
    path = PROMPT_ROOT / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing SEC-RAG v5 prompt: {path}")
    return path


class StageValidationError(ValueError):
    """A model stage exhausted format repairs while retaining its full trace."""

    def __init__(self, message: str, trace: dict[str, Any]) -> None:
        super().__init__(message)
        self.trace = trace


def call_json(
    stage: str,
    filename: str,
    model_input: Any,
    validate: Callable[[Any], dict[str, Any]],
    *,
    max_tokens: int,
    max_format_repairs: int = 2,
) -> dict[str, Any]:
    path = prompt_path(filename)
    system = path.read_text(encoding="utf-8").strip()
    messages = [
        ChatMessage("system", system),
        ChatMessage("user", json.dumps(model_input, ensure_ascii=False, indent=2)),
    ]
    trace: dict[str, Any] = {
        "stage": stage,
        "prompt": {
            "path": path.relative_to(settings.root).as_posix(),
            "sha256": sha(path),
            "messages": [message.as_dict() for message in messages],
        },
        "model_responses": [],
        "validation_errors": [],
        "parsed_output": None,
    }
    active = list(messages)
    for attempt in range(max_format_repairs + 1):
        response = DeepSeekClient().chat(active, json_output=True, max_tokens=max_tokens)
        trace["model_responses"].append(response_record(response))
        try:
            parsed = json.loads(response.content)
            trace["parsed_output"] = validate(parsed)
            trace["validation"] = {"valid": True, "format_repair_count": attempt}
            return trace
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            trace["validation_errors"].append(str(exc))
            if attempt == max_format_repairs:
                trace["validation"] = {"valid": False, "format_repair_count": attempt}
                raise StageValidationError(f"{stage} validation failed: {trace['validation_errors']}", trace) from exc
            active.extend([
                ChatMessage("assistant", response.content),
                ChatMessage("user", f"输出校验失败：{exc}。请只按原任务重新输出完整 JSON，不要添加解释。"),
            ])
    raise RuntimeError("unreachable")
