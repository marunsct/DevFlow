"""Tests for the safe product-document reader.

These tests exercise the real behavior of the document reader: it should parse
supported content, reject missing or unsupported inputs, and enforce size limits
before the workflow sends the content to an agent. That keeps the model boundary
separate from the file system and produces deterministic inputs for tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from app.documents import DocumentReadError, DocumentSizeExceeded, read_document


def test_read_markdown_document_returns_normalized_text(tmp_path: Path) -> None:
    # A markdown brief should be read as text and normalized so the graph sees a
    # predictable string instead of raw newline or spacing differences.
    file_path = tmp_path / "brief.md"
    file_path.write_text("# Product brief\n\nThis is a **demo**.\n", encoding="utf-8")

    result = read_document(file_path)

    assert result.source_type == "markdown"
    assert "Product brief" in result.text
    assert "demo" in result.text
    assert result.truncated is False


def test_read_docx_document_returns_text(tmp_path: Path) -> None:
    # A DOCX file is a binary format, so the reader must use the library that knows
    # how to decode Word documents instead of asking the model to guess the format.
    # This is still a text-only reader: it reads paragraph text, but it does not
    # extract image content or OCR screenshots inside the document.
    file_path = tmp_path / "brief.docx"
    doc = Document()
    doc.add_paragraph("The workflow should read Word input safely.")
    doc.save(file_path)

    result = read_document(file_path)

    assert result.source_type == "docx"
    assert "Word input safely" in result.text
    assert result.truncated is False


def test_read_text_document_supports_plain_text(tmp_path: Path) -> None:
    file_path = tmp_path / "brief.txt"
    file_path.write_text("Mission statement\n\nShip a useful product.\n", encoding="utf-8")

    result = read_document(file_path)

    assert result.source_type == "text"
    assert "Mission statement" in result.text
    assert "Ship a useful product" in result.text


def test_missing_file_raises_document_read_error(tmp_path: Path) -> None:
    # Missing files are not a model problem; they are a data input problem. The
    # function should fail immediately with a clear message rather than inventing text.
    missing = tmp_path / "missing.md"

    with pytest.raises(FileNotFoundError):
        read_document(missing)


def test_unsupported_extension_raises_document_read_error(tmp_path: Path) -> None:
    file_path = tmp_path / "brief.csv"
    file_path.write_text("name,value\n", encoding="utf-8")

    with pytest.raises(DocumentReadError):
        read_document(file_path)


def test_oversized_file_raises_document_size_exceeded(tmp_path: Path) -> None:
    # The safe reader must enforce size limits before handing content to the agent.
    file_path = tmp_path / "large.md"
    file_path.write_text("A" * 2048, encoding="utf-8")

    with pytest.raises(DocumentSizeExceeded):
        read_document(file_path, max_file_size_bytes=128)


def test_truncation_is_explicit_when_text_limit_is_hit(tmp_path: Path) -> None:
    file_path = tmp_path / "truncated.txt"
    file_path.write_text("word " * 6000, encoding="utf-8")

    result = read_document(file_path, max_text_chars=200)

    assert result.truncated is True
    assert "truncated" in result.truncation_note.lower()
