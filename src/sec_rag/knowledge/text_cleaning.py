"""Conservatively clean extracted guideline pages with a complete audit trail.

Raw extraction files are never changed.  This module removes only confirmed
technical noise and records every cleaning operation per page.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sec_rag.config import settings
from sec_rag.paths import ensure_parent_dir


# Exact standalone lines confirmed as publication/download artefacts.
# Medical headings and recurring clinical terms are intentionally absent.
CONFIRMED_NOISE_LINES = {"In Press", "fmx_T3RoZXJNaXJyb3Jz"}
MULTIPLE_BLANK_LINES = re.compile(r"\n{3,}")
HORIZONTAL_WHITESPACE = re.compile(r"[ \t]+")


def extracted_root() -> Path:
    return settings.knowledge_path / "extracted"


def cleaned_root() -> Path:
    return settings.knowledge_path / "cleaned"


def page_jsonl_paths() -> list[Path]:
    return sorted(extracted_root().glob("*/*.pages.jsonl"), key=lambda p: p.as_posix().lower())


def is_technical_character(character: str) -> bool:
    """Return True for characters that cannot carry usable extracted prose."""
    category = unicodedata.category(character)
    return character in {"\ufffd", "\x00"} or category == "Co" or (
        category == "Cc" and character not in "\n\r\t"
    )


def clean_page_text(raw_text: str) -> tuple[str, dict[str, object]]:
    removed_characters: Counter[str] = Counter()
    removed_lines: list[str] = []
    cleaned_lines: list[str] = []

    for original_line in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        normalized_line = " ".join(original_line.strip().split())
        if normalized_line in CONFIRMED_NOISE_LINES:
            removed_lines.append(normalized_line)
            continue

        kept_characters: list[str] = []
        for character in original_line:
            if is_technical_character(character):
                removed_characters[f"U+{ord(character):04X}"] += 1
            else:
                kept_characters.append(character)

        cleaned_line = HORIZONTAL_WHITESPACE.sub(" ", "".join(kept_characters)).strip()
        # Lines produced by broken embedded fonts contain controls mixed with
        # punctuation/Latin fragments. Removing the controls alone would leave
        # misleading gibberish, so discard the residue when no CJK character
        # and no word of at least two letters remains.
        removed_in_line = sum(is_technical_character(ch) for ch in original_line)
        has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in cleaned_line)
        has_word = bool(re.search(r"[A-Za-z]{2,}", cleaned_line))
        if removed_in_line and cleaned_line and not has_cjk and not has_word:
            removed_lines.append(cleaned_line)
            continue
        cleaned_lines.append(cleaned_line)

    clean_text = MULTIPLE_BLANK_LINES.sub("\n\n", "\n".join(cleaned_lines)).strip()
    audit = {
        "removed_technical_character_count": sum(removed_characters.values()),
        "removed_technical_characters": dict(sorted(removed_characters.items())),
        "removed_line_count": len(removed_lines),
        "removed_lines": removed_lines,
    }
    return clean_text, audit


def clean_all_pages() -> tuple[list[dict[str, object]], dict[str, object]]:
    document_summaries: list[dict[str, object]] = []
    for source_path in page_jsonl_paths():
        output_path = cleaned_root() / source_path.parent.name / source_path.name.replace(
            ".pages.jsonl", ".clean.pages.jsonl"
        )
        ensure_parent_dir(output_path)
        page_count = raw_total = clean_total = removed_chars = removed_lines = 0

        with source_path.open("r", encoding="utf-8") as source, output_path.open(
            "w", encoding="utf-8", newline="\n"
        ) as output:
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                try:
                    page = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON in {source_path}, line {line_number}: {exc}") from exc
                raw_text = str(page.get("raw_text", ""))
                clean_text, audit = clean_page_text(raw_text)
                record = {
                    "document_id": page["document_id"],
                    "disease": page["disease"],
                    "source_file": page["source_file"],
                    "page_number": page["page_number"],
                    "clean_text": clean_text,
                    "raw_character_count": len(raw_text),
                    "clean_character_count": len(clean_text),
                    **audit,
                }
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                page_count += 1
                raw_total += len(raw_text)
                clean_total += len(clean_text)
                removed_chars += int(audit["removed_technical_character_count"])
                removed_lines += int(audit["removed_line_count"])

        document_summaries.append(
            {
                "document_id": page["document_id"],
                "disease": page["disease"],
                "source_file": page["source_file"],
                "input_file": source_path.relative_to(extracted_root()).as_posix(),
                "output_file": output_path.relative_to(cleaned_root()).as_posix(),
                "page_count": page_count,
                "raw_character_count": raw_total,
                "clean_character_count": clean_total,
                "removed_technical_character_count": removed_chars,
                "removed_line_count": removed_lines,
            }
        )

    manifest = {
        "manifest_type": "guideline_conservative_text_cleaning",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_root": extracted_root().relative_to(settings.root).as_posix(),
        "output_root": cleaned_root().relative_to(settings.root).as_posix(),
        "rules": {
            "confirmed_noise_lines": sorted(CONFIRMED_NOISE_LINES),
            "technical_characters": "U+FFFD, NUL, Unicode private-use and unexpected control characters",
            "whitespace": "normalize horizontal whitespace and limit consecutive blank lines to one",
            "medical_content_policy": "do not remove repeated medical headings or clinical terms",
        },
        "document_count": len(document_summaries),
        "page_count": sum(int(d["page_count"]) for d in document_summaries),
        "raw_character_count": sum(int(d["raw_character_count"]) for d in document_summaries),
        "clean_character_count": sum(int(d["clean_character_count"]) for d in document_summaries),
        "removed_technical_character_count": sum(int(d["removed_technical_character_count"]) for d in document_summaries),
        "removed_line_count": sum(int(d["removed_line_count"]) for d in document_summaries),
        "documents": document_summaries,
    }
    manifest_path = cleaned_root() / "cleaning_manifest.json"
    ensure_parent_dir(manifest_path).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return document_summaries, manifest
