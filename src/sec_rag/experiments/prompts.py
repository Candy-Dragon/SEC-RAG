"""Load fixed, human-readable prompts from version-controlled text files."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sec_rag.config import settings


PROMPT_FILES = {
    "common": "baselines/common_system.txt",
    "llm_only": "baselines/llm_only_rules.txt",
    "traditional_rag": "baselines/traditional_rag_rules.txt",
    "prompt_constrained_rag": "baselines/prompt_constrained_rag_rules.txt",
}


def prompt_root() -> Path:
    return settings.root / "configs" / "prompts"


def load_prompt(name: str) -> str:
    path = prompt_root() / PROMPT_FILES[name]
    return path.read_text(encoding="utf-8").strip()


COMMON_SYSTEM_PROMPT = load_prompt("common")
LLM_ONLY_RULES = load_prompt("llm_only")
TRADITIONAL_RAG_RULES = load_prompt("traditional_rag")
PROMPT_CONSTRAINED_RULES = load_prompt("prompt_constrained_rag")


def system_prompt(method_rules: str) -> str:
    return f"{COMMON_SYSTEM_PROMPT}\n\n方法特定规则：\n{method_rules}"


def prompt_metadata(method: str) -> dict[str, object]:
    names = ["common", method]
    files = []
    for name in names:
        path = prompt_root() / PROMPT_FILES[name]
        content = path.read_bytes()
        files.append(
            {
                "role": name,
                "path": path.relative_to(settings.root).as_posix(),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return {"method": method, "files": files}
