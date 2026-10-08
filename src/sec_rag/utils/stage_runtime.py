from __future__ import annotations
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from sec_rag.paths import ensure_parent_dir
from sec_rag.method.constants import METHOD_CONFIG_PATH


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def concurrency_config() -> dict[str, int]:
    """Load bounded model-call concurrency from the frozen method config."""
    method = json.loads(METHOD_CONFIG_PATH.read_text(encoding="utf-8"))
    configured = method.get("concurrency", {})
    result = {
        "stage02_chunk_workers": int(configured.get("stage02_chunk_workers", 3)),
        "stage03_integrity_workers": int(configured.get("stage03_integrity_workers", 5)),
        "stage03_recovery_workers": int(configured.get("stage03_recovery_workers", 3)),
        "stage04_applicability_workers": int(configured.get("stage04_applicability_workers", 5)),
    }
    if any(value < 1 or value > 10 for value in result.values()):
        raise ValueError("SEC-RAG worker counts must be between 1 and 10")
    return result


def parallel_ordered(items: list[Any], worker: Callable[[Any], Any], max_workers: int) -> list[Any]:
    """Run independent calls concurrently while preserving input order."""
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as executor:
        return list(executor.map(worker, items))
