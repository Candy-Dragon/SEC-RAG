from __future__ import annotations
import hashlib
import re
from sec_rag.config import settings

VERSION = "sec-rag-v5-context-v1"
PROMPT_ROOT = settings.root / "configs" / "prompts" / "sec_rag_v5"
METHOD_CONFIG_PATH = settings.root / "configs" / "sec_rag_v5_context_v1.json"
LABELS = {"complete", "boundary_fragment", "uncertain"}
COVERAGE_LABELS = {"full", "partial", "none"}
SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;])|[\r\n]+")
LOADED_IMPLEMENTATION_PROVENANCE = [{"path": p.relative_to(settings.root).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((settings.root / "src/sec_rag").rglob("*.py"))]
