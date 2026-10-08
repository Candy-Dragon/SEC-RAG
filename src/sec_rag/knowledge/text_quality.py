"""Quality checks for raw page text extracted from guideline PDFs.

The checks only identify pages and repeated lines for manual review. They do
not clean text, modify source records, or create medical-content labels.
"""

from __future__ import annotations

import json
import math
import statistics
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sec_rag.config import settings
from sec_rag.paths import ensure_parent_dir


MIN_REPEATED_LINE_LENGTH = 4
MAX_REPEATED_LINE_LENGTH = 80
REPEATED_LINE_MIN_PAGES = 3
REPEATED_LINE_MIN_PAGE_RATIO = 0.20
PREVIEW_CHARACTER_LIMIT = 1200


def extracted_root() -> Path:
    return settings.knowledge_path / "extracted"


def quality_report_path() -> Path:
    return settings.knowledge_path / "quality" / "text_quality_report.json"


def page_jsonl_paths() -> list[Path]:
    return sorted(
        extracted_root().glob("*/*.pages.jsonl"),
        key=lambda path: path.as_posix().lower(),
    )


def load_pages(path: Path) -> list[dict[str, object]]:
    pages: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                pages.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path}, line {line_number}: {exc}") from exc
    return pages


def percentile(values: list[int], fraction: float) -> float:
    """Linear-interpolated percentile for a sorted numeric sequence."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def normalize_line(line: str) -> str:
    return " ".join(line.strip().split())


def repeated_line_candidates(
    pages: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Find short normalized lines repeated across many distinct pages."""
    line_pages: dict[str, set[int]] = defaultdict(set)
    for page in pages:
        page_number = int(page["page_number"])
        unique_lines = {
            normalize_line(line)
            for line in str(page.get("raw_text", "")).splitlines()
            if MIN_REPEATED_LINE_LENGTH
            <= len(normalize_line(line))
            <= MAX_REPEATED_LINE_LENGTH
        }
        for line in unique_lines:
            line_pages[line].add(page_number)

    threshold = max(
        REPEATED_LINE_MIN_PAGES,
        math.ceil(len(pages) * REPEATED_LINE_MIN_PAGE_RATIO),
    )
    candidates = [
        {
            "text": line,
            "page_count": len(page_numbers),
            "page_ratio": round(len(page_numbers) / len(pages), 4),
            "page_numbers": sorted(page_numbers),
        }
        for line, page_numbers in line_pages.items()
        if len(page_numbers) >= threshold
    ]
    return sorted(candidates, key=lambda item: (-int(item["page_count"]), str(item["text"])))


def suspicious_unicode(text: str) -> dict[str, int]:
    """Count replacement, null, private-use, and unexpected control chars."""
    return {
        "replacement_character_count": text.count("\ufffd"),
        "null_character_count": text.count("\x00"),
        "private_use_character_count": sum(
            unicodedata.category(char) == "Co" for char in text
        ),
        "unexpected_control_character_count": sum(
            unicodedata.category(char) == "Cc" and char not in "\n\r\t"
            for char in text
        ),
    }


def analyze_document(path: Path) -> dict[str, object]:
    pages = load_pages(path)
    if not pages:
        raise ValueError(f"No page records found in {path}")

    lengths = [int(page.get("character_count", 0)) for page in pages]
    q1 = percentile(lengths, 0.25)
    q3 = percentile(lengths, 0.75)
    iqr = q3 - q1
    short_threshold = max(100.0, q1 - 1.5 * iqr)
    long_threshold = q3 + 1.5 * iqr

    page_checks: list[dict[str, object]] = []
    for page in pages:
        page_number = int(page["page_number"])
        text = str(page.get("raw_text", ""))
        character_count = int(page.get("character_count", 0))
        unicode_counts = suspicious_unicode(text)
        flags: list[str] = []

        if character_count < short_threshold:
            flags.append("unusually_short")
        if character_count > long_threshold:
            flags.append("unusually_long")
        if any(unicode_counts.values()):
            flags.append("suspicious_unicode")
        if str(page.get("extraction_status", "")) != "extracted":
            flags.append("extraction_not_successful")

        if flags:
            page_checks.append(
                {
                    "page_number": page_number,
                    "character_count": character_count,
                    "flags": flags,
                    **unicode_counts,
                    "text_preview": text[:PREVIEW_CHARACTER_LIMIT],
                }
            )

    by_number = {int(page["page_number"]): page for page in pages}
    representative_numbers = {
        1,
        max(1, round(len(pages) * 0.25)),
        max(1, round(len(pages) * 0.50)),
        max(1, round(len(pages) * 0.75)),
        len(pages),
        lengths.index(min(lengths)) + 1,
        lengths.index(max(lengths)) + 1,
    }
    representative_pages = [
        {
            "page_number": number,
            "character_count": int(by_number[number].get("character_count", 0)),
            "selection_reason": "first/quartile/middle/last/min/max length",
            "text_preview": str(by_number[number].get("raw_text", ""))[
                :PREVIEW_CHARACTER_LIMIT
            ],
        }
        for number in sorted(representative_numbers)
        if number in by_number
    ]

    return {
        "document_id": pages[0]["document_id"],
        "disease": pages[0]["disease"],
        "source_file": pages[0]["source_file"],
        "page_record_file": path.relative_to(extracted_root()).as_posix(),
        "page_count": len(pages),
        "character_statistics": {
            "total": sum(lengths),
            "minimum": min(lengths),
            "q1": round(q1, 2),
            "median": round(statistics.median(lengths), 2),
            "mean": round(statistics.mean(lengths), 2),
            "q3": round(q3, 2),
            "maximum": max(lengths),
            "iqr": round(iqr, 2),
        },
        "review_thresholds": {
            "unusually_short_below": round(short_threshold, 2),
            "unusually_long_above": round(long_threshold, 2),
            "method": "Tukey 1.5*IQR fences; short threshold has a 100-character floor",
        },
        "flagged_page_count": len(page_checks),
        "flagged_pages": page_checks,
        "repeated_line_candidates": repeated_line_candidates(pages),
        "representative_pages": representative_pages,
    }


def build_quality_report() -> dict[str, object]:
    paths = page_jsonl_paths()
    documents = [analyze_document(path) for path in paths]
    return {
        "report_type": "guideline_extracted_text_quality",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Identify pages and repeated lines for manual review before cleaning",
        "automatic_checks_are_not_medical_labels": True,
        "rules": {
            "page_length_outliers": "Tukey 1.5*IQR rule within each document",
            "suspicious_unicode": "U+FFFD, NUL, private-use, or unexpected control characters",
            "repeated_lines": (
                "normalized lines of 4-80 characters appearing on at least "
                "max(3 pages, 20% of document pages)"
            ),
            "text_preview_limit": PREVIEW_CHARACTER_LIMIT,
        },
        "document_count": len(documents),
        "page_count": sum(int(document["page_count"]) for document in documents),
        "flagged_page_count": sum(
            int(document["flagged_page_count"]) for document in documents
        ),
        "documents": documents,
    }


def write_quality_report(report: dict[str, object]) -> Path:
    path = ensure_parent_dir(quality_report_path())
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path

