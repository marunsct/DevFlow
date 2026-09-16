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
    source_type: Literal["markdown", "text", "docx", "pdf", "csv"]
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
    # Trailing whitespace and line endings are normalised; leading indentation
    # is preserved. Stripping every line flattened fenced code blocks and nested
    # lists in the product brief before any agent saw it.
    return "\n".join(line.rstrip() for line in raw_text.splitlines()).strip()


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


def _read_pdf_file(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text)
    return "\n".join(pages_text)


def _read_csv_file(path: Path) -> str:
    import csv
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        lines = [",".join(row) for row in reader]
    return "\n".join(lines)


def _ensure_supported_type(path: Path) -> Literal["markdown", "text", "docx", "pdf", "csv"]:
    """Recognize the supported source types and reject anything else early."""
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "markdown"
    if suffix == ".txt":
        return "text"
    if suffix == ".docx":
        return "docx"
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".csv":
        return "csv"
    raise DocumentReadError(
        f"Unsupported document type for '{path.name}'. Supported types are .md, .txt, .docx, .pdf, and .csv."
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
        elif source_type == "docx":
            raw_text = _read_docx_file(file_path)
        elif source_type == "pdf":
            raw_text = _read_pdf_file(file_path)
        elif source_type == "csv":
            raw_text = _read_csv_file(file_path)
        else:
            raise DocumentReadError(f"Unsupported document type: {source_type}")
            
        # Numbered, never named. `file_path.name` is the *stored* upload name -
        # `brief_low_236ab395.md` - which exists nowhere an agent can read, and
        # a filename in a prompt is an affordance: it invites a read.
        #
        # Measured across runs 2b5def74, da6c5e19, 5d83e946, 36eb1260 and
        # 3ddd443f: `product_manager` opens by trying to read that exact string
        # and gets an error for its first call of the run. A previous fix
        # removed the name from the brief that wraps this text; the name was in
        # the text itself, and only the run transcript showed that.
        #
        # A separator is still needed when several documents are combined, so
        # it stays - as an ordinal, which tells the model what it needs (where
        # one document ends) without naming a file it cannot open.
        combined_text.append(
            f"--- Document {len(combined_text) + 1} ---\n{_normalize_text(raw_text)}"
        )

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
