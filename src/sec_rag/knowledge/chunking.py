"""Build traceable retrieval chunks from cleaned guideline pages."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sec_rag.config import settings
from sec_rag.paths import ensure_parent_dir


SENTENCE_END = re.compile(r"(?<=[。！？；!?])")
CHAPTER_HEADING = re.compile(r"^第[一二三四五六七八九十百0-9]+[章节篇部分].{0,55}$")
STRONG_HEADING = re.compile(
    r"^(第[一二三四五六七八九十百0-9]+[章节篇部分]|[一二三四五六七八九十百]+、).{0,55}$"
)


@dataclass(frozen=True)
class TextUnit:
    text: str
    page_number: int
    heading: str


def cleaned_root() -> Path:
    return settings.knowledge_path / "cleaned"


def chunks_root() -> Path:
    return settings.knowledge_path / "chunks"


def config_path() -> Path:
    return settings.root / "configs" / "knowledge_chunking.json"


def load_config() -> dict[str, object]:
    config = json.loads(config_path().read_text(encoding="utf-8"))
    maximum = int(config["max_characters"])
    overlap = int(config["overlap_characters"])
    if maximum <= 0 or overlap < 0 or overlap >= maximum:
        raise ValueError("Require max_characters > overlap_characters >= 0")
    return config


def apply_content_exclusions(
    pages: list[dict[str, object]], config: dict[str, object]
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Apply explicit, document-specific exclusions without changing clean files."""
    if not pages:
        return pages, {"excluded_pages": [], "excluded_text_blocks": []}
    document_id = str(pages[0]["document_id"])
    rules = dict(config.get("content_exclusions", {})).get(document_id, {})
    whole_pages = {int(value) for value in rules.get("whole_pages", [])}
    block_rules = list(rules.get("text_blocks", []))
    retained: list[dict[str, object]] = []
    audit: dict[str, object] = {
        "excluded_pages": sorted(whole_pages),
        "excluded_text_blocks": [],
    }
    for source_page in pages:
        page = dict(source_page)
        page_number = int(page["page_number"])
        if page_number in whole_pages:
            continue
        text = str(page.get("clean_text", ""))
        for rule in block_rules:
            if int(rule["page_number"]) != page_number:
                continue
            start_marker = str(rule["start_marker"])
            end_marker = str(rule["end_marker"])
            start = text.find(start_marker)
            end = text.find(end_marker, start + len(start_marker)) if start >= 0 else -1
            if start < 0 or end < 0:
                raise ValueError(
                    f"Configured exclusion markers not found: {document_id}, page {page_number}"
                )
            removed = text[start:end]
            text = (text[:start] + text[end:]).strip()
            audit["excluded_text_blocks"].append(
                {
                    "page_number": page_number,
                    "reason": rule["reason"],
                    "removed_character_count": len(removed),
                    "start_marker": start_marker,
                    "end_marker": end_marker,
                }
            )
        page["clean_text"] = text
        retained.append(page)
    return retained, audit


def cleaned_page_paths() -> list[Path]:
    return sorted(cleaned_root().glob("*/*.clean.pages.jsonl"), key=lambda p: p.as_posix().lower())


def split_long_piece(text: str, maximum: int) -> list[str]:
    """Split an overlong sentence at punctuation when possible, then hard-limit."""
    pieces: list[str] = []
    remaining = text.strip()
    while len(remaining) > maximum:
        window = remaining[:maximum]
        cut = max(window.rfind(mark) for mark in "，、：,:") + 1
        if cut < maximum // 2:
            cut = maximum
        pieces.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


def pages_to_units(pages: list[dict[str, object]], maximum: int) -> list[TextUnit]:
    units: list[TextUnit] = []
    current_heading = ""
    for page in pages:
        page_number = int(page["page_number"])
        for raw_line in str(page.get("clean_text", "")).splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            if STRONG_HEADING.match(line):
                current_heading = line
            sentences = [part.strip() for part in SENTENCE_END.split(line) if part.strip()]
            for sentence in sentences:
                for piece in split_long_piece(sentence, maximum):
                    units.append(TextUnit(piece, page_number, current_heading))
    return units


def joined_length(units: list[TextUnit]) -> int:
    return sum(len(unit.text) for unit in units) + max(0, len(units) - 1)


def pack_units(
    units: list[TextUnit], maximum: int, overlap: int, keep_section_heading: bool
) -> list[list[TextUnit]]:
    chunks: list[list[TextUnit]] = []
    start = 0
    while start < len(units):
        end = start
        current: list[TextUnit] = []
        stopped_at_heading = False
        while end < len(units):
            if (
                keep_section_heading
                and current
                and CHAPTER_HEADING.match(units[end].text)
                and units[end].text != current[0].heading
            ):
                stopped_at_heading = True
                break
            candidate = current + [units[end]]
            if current and joined_length(candidate) > maximum:
                break
            current = candidate
            end += 1
        chunks.append(current)
        if end >= len(units):
            break

        # Do not carry overlap from the preceding section into a new section.
        if stopped_at_heading:
            start = end
            continue

        overlap_start = end
        overlap_units: list[TextUnit] = []
        while overlap_start > start:
            candidate = [units[overlap_start - 1]] + overlap_units
            if joined_length(candidate) > overlap:
                break
            overlap_start -= 1
            overlap_units = candidate
        start = overlap_start if overlap_start > start else end
    return chunks


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def build_all_chunks() -> tuple[list[dict[str, object]], dict[str, object]]:
    config = load_config()
    maximum = int(config["max_characters"])
    overlap = int(config["overlap_characters"])
    summaries: list[dict[str, object]] = []

    for source_path in cleaned_page_paths():
        source_pages = [json.loads(line) for line in source_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not source_pages:
            continue
        pages, exclusion_audit = apply_content_exclusions(source_pages, config)
        units = pages_to_units(pages, maximum)
        packed = pack_units(
            units, maximum, overlap, bool(config["keep_section_heading"])
        )
        output_path = chunks_root() / source_path.parent.name / source_path.name.replace(
            ".clean.pages.jsonl", ".chunks.jsonl"
        )
        ensure_parent_dir(output_path)
        with output_path.open("w", encoding="utf-8", newline="\n") as output:
            for index, chunk_units in enumerate(packed, start=1):
                text = " ".join(unit.text for unit in chunk_units)
                page_numbers = sorted({unit.page_number for unit in chunk_units})
                headings = [unit.heading for unit in chunk_units if unit.heading]
                section_heading = headings[0] if headings else ""
                identity = f"{pages[0]['document_id']}|{index}|{text}".encode("utf-8")
                record = {
                    "chunk_id": hashlib.sha256(identity).hexdigest()[:20],
                    "document_id": pages[0]["document_id"],
                    "disease": pages[0]["disease"],
                    "source_file": pages[0]["source_file"],
                    "chunk_index": index,
                    "page_start": min(page_numbers),
                    "page_end": max(page_numbers),
                    "page_numbers": page_numbers,
                    "section_heading": section_heading,
                    "text": text,
                    "character_count": len(text),
                }
                output.write(json.dumps(record, ensure_ascii=False) + "\n")

        lengths = [joined_length(chunk) for chunk in packed]
        summaries.append(
            {
                "document_id": pages[0]["document_id"],
                "disease": pages[0]["disease"],
                "source_file": pages[0]["source_file"],
                "input_file": source_path.relative_to(cleaned_root()).as_posix(),
                "input_sha256": file_sha256(source_path),
                "output_file": output_path.relative_to(chunks_root()).as_posix(),
                "source_page_count": len(source_pages),
                "indexed_page_count": len(pages),
                "content_exclusion_audit": exclusion_audit,
                "chunk_count": len(packed),
                "minimum_chunk_characters": min(lengths),
                "maximum_chunk_characters": max(lengths),
                "mean_chunk_characters": round(sum(lengths) / len(lengths), 2),
            }
        )

    manifest = {
        "manifest_type": "guideline_retrieval_chunks",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "configuration_file": config_path().relative_to(settings.root).as_posix(),
        "configuration": config,
        "document_count": len(summaries),
        "source_page_count": sum(int(item["source_page_count"]) for item in summaries),
        "indexed_page_count": sum(int(item["indexed_page_count"]) for item in summaries),
        "chunk_count": sum(int(item["chunk_count"]) for item in summaries),
        "documents": summaries,
    }
    manifest_path = chunks_root() / "chunk_manifest.json"
    ensure_parent_dir(manifest_path).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summaries, manifest
