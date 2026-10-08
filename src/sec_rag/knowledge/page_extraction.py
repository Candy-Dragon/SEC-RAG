"""Extract raw text from every guideline PDF page.

The extracted text is intentionally uncleaned. Each JSONL record represents
one PDF page so later cleaning and chunking remain traceable to the source.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

from sec_rag.config import settings
from sec_rag.paths import ensure_parent_dir


@dataclass(frozen=True)
class ExtractedPage:
    document_id: str
    disease: str
    source_file: str
    page_number: int
    raw_text: str
    character_count: int
    extraction_status: str
    error_message: str


@dataclass(frozen=True)
class ExtractedDocument:
    document_id: str
    disease: str
    source_file: str
    source_relative_path: str
    source_sha256: str
    page_count: int
    extracted_page_count: int
    empty_page_count: int
    error_page_count: int
    extracted_character_count: int
    output_relative_path: str


def guideline_pdf_paths() -> list[Path]:
    """Return all source guideline PDFs in deterministic path order."""
    root = settings.knowledge_documents
    return sorted(
        (path for path in root.rglob("*.pdf") if path.is_file()),
        key=lambda path: path.as_posix().lower(),
    )


def file_sha256(path: Path, block_size: int = 1024 * 1024) -> str:
    """Calculate the source PDF's reproducible SHA-256 fingerprint."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def extracted_root() -> Path:
    return settings.knowledge_path / "extracted"


def extract_pdf_pages(path: Path) -> tuple[list[ExtractedPage], str]:
    """Extract one PDF into page records and return its stable document ID."""
    source_root = settings.knowledge_documents
    disease = path.parent.name
    sha256 = file_sha256(path)
    document_id = f"{disease}_{sha256[:12]}"
    pages: list[ExtractedPage] = []

    reader = PdfReader(path)
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            raw_text = page.extract_text() or ""
            status = "extracted" if raw_text.strip() else "empty"
            error_message = ""
        except Exception as exc:
            raw_text = ""
            status = "error"
            error_message = f"{type(exc).__name__}: {exc}"

        pages.append(
            ExtractedPage(
                document_id=document_id,
                disease=disease,
                source_file=path.name,
                page_number=page_number,
                raw_text=raw_text,
                character_count=len(raw_text),
                extraction_status=status,
                error_message=error_message,
            )
        )

    return pages, document_id


def page_output_path(disease: str, document_id: str) -> Path:
    return extracted_root() / disease / f"{document_id}.pages.jsonl"


def write_page_records(pages: list[ExtractedPage], output_path: Path) -> Path:
    path = ensure_parent_dir(output_path)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for page in pages:
            handle.write(json.dumps(asdict(page), ensure_ascii=False) + "\n")
    return path


def extract_all_guidelines() -> list[ExtractedDocument]:
    """Extract every guideline and return one manifest record per document."""
    source_root = settings.knowledge_documents
    output_root = extracted_root()
    documents: list[ExtractedDocument] = []

    for path in guideline_pdf_paths():
        pages, document_id = extract_pdf_pages(path)
        disease = path.parent.name
        output_path = write_page_records(
            pages, page_output_path(disease, document_id)
        )

        documents.append(
            ExtractedDocument(
                document_id=document_id,
                disease=disease,
                source_file=path.name,
                source_relative_path=path.relative_to(source_root).as_posix(),
                source_sha256=file_sha256(path),
                page_count=len(pages),
                extracted_page_count=sum(
                    page.extraction_status == "extracted" for page in pages
                ),
                empty_page_count=sum(
                    page.extraction_status == "empty" for page in pages
                ),
                error_page_count=sum(
                    page.extraction_status == "error" for page in pages
                ),
                extracted_character_count=sum(
                    page.character_count for page in pages
                ),
                output_relative_path=output_path.relative_to(output_root).as_posix(),
            )
        )

    return documents


def manifest_path() -> Path:
    return extracted_root() / "extraction_manifest.json"


def write_extraction_manifest(documents: list[ExtractedDocument]) -> Path:
    path = ensure_parent_dir(manifest_path())
    payload = {
        "manifest_type": "guideline_page_extraction",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_root": settings.knowledge_documents.relative_to(settings.root).as_posix(),
        "output_root": extracted_root().relative_to(settings.root).as_posix(),
        "tool": "pypdf",
        "tool_version": __import__("pypdf").__version__,
        "document_count": len(documents),
        "page_count": sum(document.page_count for document in documents),
        "extracted_character_count": sum(
            document.extracted_character_count for document in documents
        ),
        "documents": [asdict(document) for document in documents],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path
