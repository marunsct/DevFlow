"""Safe document loading for product briefs and other workflow inputs.

A beginner-friendly summary: this module is intentionally text-only. It reads
plain text, Markdown, and DOCX content, but it does not inspect embedded images,
charts, or diagrams. If a product brief contains screenshots or visual mockups,
that data must be handled by a separate image-analysis step rather than by this
reader. The goal here is deterministic, testable text extraction, not full
multimodal document understanding.

The workflow should never ask a model to inspect binary files or guess file types.
Instead, this module centralizes the deterministic parsing logic: it validates the
file extension, reads the file using the right library, normalizes content, and
applies strict limits before any downstream node sees the text.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from docx import Document as DocxDocument


class DocumentReadError(ValueError):
    """Raised when a file is missing, unsupported, or cannot be parsed safely."""


class DocumentSizeExceeded(DocumentReadError):
    """Raised when the file or extracted text exceeds the configured safety cap."""


@dataclass(frozen=True)
class DocumentContent:
    """Normalized document payload returned to workflow stages.

    This object keeps the source metadata and the rendered text together so a node
    can inspect both the original file and the extracted content without losing
    the provenance needed for audits or debugging.
    """

    source_path: str
    source_type: Literal["markdown", "text", "docx"]
    text: str
    truncated: bool
    truncation_note: str | None = None
    file_size_bytes: int | None = None


def _normalize_text(raw_text: str) -> str:
    """Convert file content into a stable text format for downstream reasoning.

    We collapse repeated whitespace so the same document produces the same content
    regardless of the user's line endings or copy-paste formatting. This makes the
    output easier to test and less surprising for the model.
    """
    return "\n".join(line.strip() for line in raw_text.splitlines()).strip()


def _read_markdown(path: Path) -> str:
    """Read a Markdown file directly as UTF-8 text."""
    return path.read_text(encoding="utf-8")


def _read_text_file(path: Path) -> str:
    """Read a plain-text file using the platform default UTF-8 decoding."""
    return path.read_text(encoding="utf-8")


def _read_docx_file(path: Path) -> str:
    """Read a DOCX file by using python-docx, not an LLM or a file-guessing heuristic.

    Important limitation: this helper extracts text from the document body only.
    It does not OCR or inspect images, screenshots, or embedded diagrams. If a
    future product brief includes visuals, a separate image-processing step should
    convert that content into text before the workflow uses it.
    """
    document = DocxDocument(str(path))
    # python-docx exposes paragraph text but not image semantics. This is a text
    # extraction helper, not a multimodal document reader.
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    return "\n".join(paragraphs)


def _ensure_supported_type(path: Path) -> Literal["markdown", "text", "docx"]:
    """Recognize the supported source types and reject anything else early."""
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "markdown"
    if suffix == ".txt":
        return "text"
    if suffix == ".docx":
        return "docx"
    raise DocumentReadError(
        f"Unsupported document type for '{path.name}'. Supported types are .md, .txt, and .docx."
    )


def read_document(
    paths: str | Path | list[str | Path],
    *,
    max_file_size_bytes: int = 5 * 1024 * 1024,
    max_text_chars: int = 250_000,
) -> DocumentContent:
    """Safely read product document(s) and return normalized text with metadata."""
    if not isinstance(paths, list):
        paths = [paths]
        
    combined_text = []
    total_size = 0
    source_types = set()
    truncated = False
    
    for path in paths:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")
        if not file_path.is_file():
            raise DocumentReadError(f"Path is not a regular file: {file_path}")

        source_type = _ensure_supported_type(file_path)
        source_types.add(source_type)
        
        file_size_bytes = file_path.stat().st_size
        total_size += file_size_bytes
        
        if file_size_bytes > max_file_size_bytes:
            raise DocumentSizeExceeded(
                f"Document '{file_path.name}' is {file_size_bytes} bytes; the limit is {max_file_size_bytes} bytes."
            )

        if source_type == "markdown":
            raw_text = _read_markdown(file_path)
        elif source_type == "text":
            raw_text = _read_text_file(file_path)
        else:
            raw_text = _read_docx_file(file_path)
            
        combined_text.append(f"--- Document: {file_path.name} ---\n{_normalize_text(raw_text)}")

    normalized_text = "\n\n".join(combined_text)
    truncation_note = None

    if len(normalized_text) > max_text_chars:
        truncated = True
        truncation_note = (
            f"Text was truncated to {max_text_chars} characters to preserve a safe size limit."
        )
        normalized_text = normalized_text[:max_text_chars]

    # Use the first source path for metadata representation or a comma-separated list
    primary_source_path = str(paths[0]) if len(paths) == 1 else ", ".join([Path(p).name for p in paths])
    primary_source_type = list(source_types)[0] if len(source_types) == 1 else "markdown"

    return DocumentContent(
        source_path=primary_source_path,
        source_type=primary_source_type, # type: ignore
        text=normalized_text,
        truncated=truncated,
        truncation_note=truncation_note,
        file_size_bytes=total_size,
    )


__all__ = [
    "DocumentContent",
    "DocumentReadError",
    "DocumentSizeExceeded",
    "read_document",
]
