"""Small, auditable client for DeepSeek's OpenAI-compatible chat endpoint."""

from __future__ import annotations

import time
from typing import Any

import httpx

from sec_rag.config import settings
from sec_rag.llm.types import ChatMessage, ModelResponse, ModelUsage


RETRYABLE_STATUS_CODES = {429, 500, 503}


class DeepSeekAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class DeepSeekClient:
    def __init__(self) -> None:
        if not settings.model_api_key:
            raise ValueError("MODEL_API_KEY is empty. Configure it in .env.")
        self.endpoint = f"{settings.model_base_url.rstrip('/')}/chat/completions"

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_output: bool = False,
    ) -> ModelResponse:
        if not messages:
            raise ValueError("At least one chat message is required.")
        payload: dict[str, Any] = {
            "model": settings.model_name,
            "messages": [message.as_dict() for message in messages],
            "temperature": settings.model_temperature if temperature is None else temperature,
            "max_tokens": settings.model_max_output_tokens if max_tokens is None else max_tokens,
            "stream": False,
            "thinking": {"type": "disabled"},
        }
        if json_output:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {settings.model_api_key}",
            "Content-Type": "application/json",
        }
        started = time.perf_counter()
        last_error: Exception | None = None
        maximum_attempts = settings.model_max_retries + 1

        with httpx.Client(timeout=settings.model_timeout_seconds) as client:
            for attempt in range(1, maximum_attempts + 1):
                try:
                    response = client.post(self.endpoint, headers=headers, json=payload)
                    if response.status_code >= 400:
                        detail = _safe_error_detail(response)
                        error = DeepSeekAPIError(
                            f"DeepSeek API returned HTTP {response.status_code}: {detail}",
                            response.status_code,
                        )
                        if response.status_code in RETRYABLE_STATUS_CODES and attempt < maximum_attempts:
                            last_error = error
                            time.sleep(min(2 ** (attempt - 1), 4))
                            continue
                        raise error
                    body = response.json()
                    return _parse_response(
                        body,
                        requested_model=settings.model_name,
                        latency_seconds=time.perf_counter() - started,
                        attempt_count=attempt,
                    )
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_error = exc
                    if attempt < maximum_attempts:
                        time.sleep(min(2 ** (attempt - 1), 4))
                        continue
                    raise DeepSeekAPIError(f"DeepSeek network request failed: {exc}") from exc

        raise DeepSeekAPIError(f"DeepSeek request failed: {last_error}")


def _safe_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return str(payload.get("error", payload))[:500]
    except ValueError:
        return response.text[:500]


def _parse_response(
    body: dict[str, Any], requested_model: str, latency_seconds: float, attempt_count: int
) -> ModelResponse:
    try:
        choice = body["choices"][0]
        message = choice["message"]
        usage_data = body.get("usage") or {}
        usage = ModelUsage(
            prompt_tokens=int(usage_data.get("prompt_tokens", 0)),
            completion_tokens=int(usage_data.get("completion_tokens", 0)),
            total_tokens=int(usage_data.get("total_tokens", 0)),
            prompt_cache_hit_tokens=usage_data.get("prompt_cache_hit_tokens"),
            prompt_cache_miss_tokens=usage_data.get("prompt_cache_miss_tokens"),
        )
        return ModelResponse(
            request_id=str(body.get("id", "")),
            requested_model=requested_model,
            returned_model=str(body.get("model", "")),
            content=str(message.get("content") or ""),
            reasoning_content=message.get("reasoning_content"),
            finish_reason=str(choice.get("finish_reason", "")),
            usage=usage,
            latency_seconds=round(latency_seconds, 4),
            attempt_count=attempt_count,
            raw_response=body,
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise DeepSeekAPIError(f"Unexpected DeepSeek response structure: {exc}") from exc

