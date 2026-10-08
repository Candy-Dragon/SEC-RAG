"""Explicit request and response records for reproducible model calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class ModelUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_cache_hit_tokens: int | None = None
    prompt_cache_miss_tokens: int | None = None


@dataclass(frozen=True)
class ModelResponse:
    request_id: str
    requested_model: str
    returned_model: str
    content: str
    reasoning_content: str | None
    finish_reason: str
    usage: ModelUsage
    latency_seconds: float
    attempt_count: int
    raw_response: dict[str, Any]

