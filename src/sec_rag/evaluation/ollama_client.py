from __future__ import annotations

import json
import hashlib
import uuid
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx


class LocalJudgeError(RuntimeError):
    def __init__(self, message: str, trace: dict[str, Any]):
        super().__init__(message)
        self.trace = trace


class OllamaJudge:
    def __init__(self, model: str = "qwen3:4b-instruct", base_url: str = "http://127.0.0.1:11434", cache_dir: Path | None = None):
        self.model, self.base_url = model, base_url.rstrip("/")
        # Local inference must not inherit HTTP_PROXY/HTTPS_PROXY/ALL_PROXY.
        self.trust_env = urlsplit(self.base_url).hostname not in ("localhost", "127.0.0.1", "::1")
        self.cache_dir = cache_dir
        self.model_digest = None

    def check(self) -> dict[str, Any]:
        url = f"{self.base_url}/api/tags"
        try:
            response = httpx.get(url, timeout=10, trust_env=self.trust_env)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Ollama model-list endpoint returned HTTP {exc.response.status_code}: {url}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama at {url} ({type(exc).__name__}). "
                "Open Ollama, or run 'ollama serve' in another terminal, then retry. "
                "Local requests bypass environment proxies."
            ) from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Ollama model-list endpoint returned non-JSON data: {url}; "
                f"HTTP {response.status_code}, content-type={response.headers.get('content-type', 'unknown')}. "
                "Check that this port is served by Ollama."
            ) from exc
        if not isinstance(data, dict) or not isinstance(data.get("models"), list) or any(
            not isinstance(item, dict) or not isinstance(item.get("name"), str) for item in data["models"]
        ):
            raise RuntimeError(f"Invalid Ollama model-list response at {url}: expected a models list")
        names = [item["name"] for item in data.get("models", [])]
        if self.model not in names:
            raise RuntimeError(f"Required Ollama model {self.model!r} not found; installed={names}")
        self.model_digest = next(item.get("digest") for item in data["models"] if item["name"] == self.model)
        return {"base_url": self.base_url, "required_model": self.model, "installed_models": names}

    def call_json(self, prompt_path: Path, payload: dict[str, Any], validator: Callable[[Any], Any], *, schema: dict | None = None) -> dict[str, Any]:
        system = prompt_path.read_text(encoding="utf-8").strip()
        messages = [{"role": "system", "content": "/no_think\n" + system},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}]
        key = hashlib.sha256(json.dumps({"version":2,"model":self.model,"digest":self.model_digest,"messages":messages,"format":schema or "json",
            "options":{"temperature":0,"seed":42,"num_ctx":8192}}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        cache = self.cache_dir / (key + ".json") if self.cache_dir and self.model_digest else None
        if cache and cache.exists():
            saved = json.loads(cache.read_text(encoding="utf-8"))
            try:
                saved["parsed"] = validator(saved["parsed"])
                saved["cache_hit"] = True
                return saved
            except (ValueError, TypeError, KeyError):
                pass
        trace: dict[str, Any] = {"model": self.model, "prompt_path": str(prompt_path), "messages": messages,
                                "responses": [], "errors": [], "cache_key": key, "model_digest":self.model_digest,"cache_hit":False}
        active = list(messages)
        for attempt in range(3):
            started = time.perf_counter()
            response = httpx.post(f"{self.base_url}/api/chat", json={"model": self.model, "messages": active,
                "stream": False, "format": schema or "json", "keep_alive":"30m", "options": {"temperature": 0, "seed": 42, "num_ctx": 8192}}, timeout=300, trust_env=self.trust_env)
            response.raise_for_status()
            raw = response.json()
            trace["responses"].append({"attempt": attempt + 1, "elapsed_seconds": time.perf_counter() - started,
                "prompt_eval_count": raw.get("prompt_eval_count"), "eval_count": raw.get("eval_count"),
                "content": raw.get("message", {}).get("content", ""), "done_reason": raw.get("done_reason")})
            try:
                parsed = json.loads(trace["responses"][-1]["content"])
                trace["parsed"] = validator(parsed)
                trace["status"] = "completed"
                if cache:
                    cache.parent.mkdir(parents=True,exist_ok=True)
                    temporary = cache.with_suffix(f".{uuid.uuid4().hex}.tmp")
                    temporary.write_text(json.dumps(trace,ensure_ascii=False,indent=2),encoding="utf-8")
                    temporary.replace(cache)
                return trace
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                trace["errors"].append(str(exc))
                active.extend([{"role": "assistant", "content": trace["responses"][-1]["content"]},
                               {"role": "user", "content": f"JSON校验失败：{exc}。只输出修正后的完整JSON。"}])
        trace["status"] = "failed"
        raise LocalJudgeError("Local judge exhausted JSON repairs", trace)
