"""Tests for incremental document filling and continuation after cutoff or repair."""

import re
import pytest
from app.agents.principal_architect import TechnicalSpecificationOutput
from app.graph.workflow import _with_the_sections_it_dropped
from app.models.tool_arguments import cut_off_notice, _sync_partial_document

BANNED_WORDS = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.IGNORECASE)


def test_technical_specification_output_allows_partial_repair():
    """A repair providing only specialist_advice_decisions should validate without requiring product_scope."""
    partial = TechnicalSpecificationOutput(
        specialist_advice_decisions=["DB-1: adopted in store.js", "TS-1: adopted in tests/"]
    )
    assert partial.specialist_advice_decisions == ["DB-1: adopted in store.js", "TS-1: adopted in tests/"]
    assert partial.product_scope == ""


def test_with_the_sections_it_dropped_preserves_product_scope_and_all_sections():
    """Omitted sections including product_scope and list fields are preserved from previous specification."""
    previous = TechnicalSpecificationOutput(
        product_scope="Full original scope",
        component_boundaries=["Boundary A"],
        file_plan=["file1.js"],
        specialist_advice_decisions=[],
    )
    revised = TechnicalSpecificationOutput(
        specialist_advice_decisions=["DB-1: adopted in store.js"],
    )
    merged = _with_the_sections_it_dropped(revised, previous)
    assert merged.product_scope == "Full original scope"
    assert merged.component_boundaries == ["Boundary A"]
    assert merged.file_plan == ["file1.js"]
    assert merged.specialist_advice_decisions == ["DB-1: adopted in store.js"]


def test_sync_partial_document_writes_partial_doc_and_cut_off_notice_has_no_banned_words(tmp_path):
    """When fields arrive whole, the partial document is written to disk and cut_off_notice mentions it without banned words."""
    doc_file = tmp_path / "docs" / "technical_specification.md"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    
    held = {
        "product_scope": "Initial scope",
        "component_boundaries": ["Boundary 1"],
    }
    key = ("run-test", "principal_architect", "TechnicalSpecificationOutput")
    from app.models.tool_arguments import _HELD, CUT_OFF
    _HELD[key] = held
    written = _sync_partial_document(
        key=key,
        held=held,
        workspace_override=tmp_path,
    )
    assert written == "docs/technical_specification.md"
    assert doc_file.exists()
    content = doc_file.read_text()
    assert "Initial scope" in content
    assert "Boundary 1" in content

    notice = cut_off_notice(
        Exception(f"Stopped due to {CUT_OFF}"),
        TechnicalSpecificationOutput,
        key=key,
    )
    assert notice is not None
    assert "docs/technical_specification.md" in notice
    assert "Do not start over" in notice
    matches = BANNED_WORDS.findall(notice)
    assert matches == []


def test_sync_partial_document_updates_project_memory_seamlessly(tmp_path):
    """When a document is partially written to disk, project memory picks it up immediately."""
    from app.agents import project_memory
    doc_file = tmp_path / "docs" / "technical_specification.md"
    doc_file.parent.mkdir(parents=True, exist_ok=True)

    held = {
        "product_scope": "Initial scope in progress",
        "file_plan": ["src/index.js", "src/store.js"],
    }
    key = ("run-mem-test", "principal_architect", "TechnicalSpecificationOutput")
    from app.models.tool_arguments import _HELD
    _HELD[key] = held
    _sync_partial_document(
        key=key,
        held=held,
        workspace_override=tmp_path,
    )

    memory_files = project_memory.current(tmp_path)
    assert "docs/technical_specification.md" in memory_files
    assert "Initial scope in progress" in memory_files["docs/technical_specification.md"]
    assert "src/store.js" in memory_files["docs/technical_specification.md"]

    text, held_rendered = project_memory.render(
        repo_root=tmp_path,
        budget_characters=10000,
        focus="specification",
    )
    assert "docs/technical_specification.md" in text
    assert "Initial scope in progress" in text
    assert "docs/technical_specification.md" in held_rendered
