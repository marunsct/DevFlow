"""`grep` matches a pattern written as a regular expression when no line holds it as plain text (TR.5).

Measured over 26 runs (tool review 2026-11-26): 31 of 69 patterns written as regular expressions found nothing (45%),
against 15 of 74 plain ones. One architecture review asked `^## ` of its technical specification seven times, each
answered "No matches found", while the specification's sections are `## ` lines. The files here are captured from
run workspaces: that specification's head, and a Rust handler file a fixer searched with `^async fn list_notes`.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.agents.workspace_backend import WorkspaceBackend
from tests.a_role_agent import run_a_role_agent

CAPTURED = Path(__file__).parent / "captured"


def _workspace(root: Path) -> Path:
    (root / "docs").mkdir()
    shutil.copy(CAPTURED / "technical_specification_head.md", root / "docs" / "technical_specification.md")
    (root / "notes-api" / "src").mkdir(parents=True)
    shutil.copy(CAPTURED / "notes_handlers_excerpt.rs", root / "notes-api" / "src" / "handlers.rs")
    return root


def _texts(result) -> list[str]:
    return [match["text"] for match in result.matches or []]


def test_an_anchored_heading_pattern_finds_the_headings(tmp_path):
    backend = WorkspaceBackend(root_dir=str(_workspace(tmp_path)), virtual_mode=True)

    result = backend.grep("^## ", path="/docs/technical_specification.md")

    assert _texts(result) == ["## Product Scope", "## Component Boundaries", "## Domain Model",
                              "## API and Event Contracts"]


def test_a_wildcard_pattern_finds_its_line_across_the_workspace(tmp_path):
    backend = WorkspaceBackend(root_dir=str(_workspace(tmp_path)), virtual_mode=True)

    result = backend.grep("fn list_.*AppState", path="/")

    assert [(m["path"], m["line"]) for m in result.matches] == [("/notes-api/src/handlers.rs", 9)]


def test_text_that_is_there_as_written_is_found_as_written(tmp_path):
    backend = WorkspaceBackend(root_dir=str(_workspace(tmp_path)), virtual_mode=True)

    result = backend.grep("list_notes(", path="/notes-api")

    assert _texts(result) == ["pub async fn list_notes(State(state): State<AppState>) -> Json<Vec<Note>> {",
                              "    let notes = store.list_notes();"]


def test_a_pattern_that_is_not_a_valid_expression_finds_nothing_and_raises_nothing(tmp_path):
    backend = WorkspaceBackend(root_dir=str(_workspace(tmp_path)), virtual_mode=True)

    result = backend.grep("list_notes(Query(", path="/notes-api")

    assert result.matches == [] and not result.error


def test_package_caches_are_not_searched_as_an_expression(tmp_path):
    root = _workspace(tmp_path)
    (root / "node_modules" / "x").mkdir(parents=True)
    (root / "node_modules" / "x" / "README.md").write_text("## Install\n", encoding="utf-8")
    backend = WorkspaceBackend(root_dir=str(root), virtual_mode=True)

    result = backend.grep("^## Inst", path="/")

    assert result.matches == []


def _the_answer_to(tmp_path, monkeypatch, pattern: str, path: str) -> str:
    call = AIMessage(content="", tool_calls=[{"name": "grep", "args": {"pattern": pattern, "path": path}, "id": "g1"}])
    requests = run_a_role_agent(_workspace(tmp_path), monkeypatch, [call])
    return next(m.content for m in requests[1] if isinstance(m, ToolMessage))


def test_the_stage_is_told_its_pattern_matched_as_an_expression(tmp_path, monkeypatch):
    answer = _the_answer_to(tmp_path, monkeypatch, "^## ", "/docs/technical_specification.md")

    assert "## Domain Model" in answer
    assert "regular expression" in answer


def test_an_anchor_that_matches_nowhere_is_said_to_have_been_tried_both_ways(tmp_path, monkeypatch):
    """The fixer's `^async fn list_notes`: the line starts `pub async fn`, so nothing matches either way."""
    answer = _the_answer_to(tmp_path, monkeypatch, "^async fn list_notes", "/notes-api")

    assert "plain text and as a regular expression" in answer
    assert "literal text, not regex" not in answer


def test_an_invalid_expression_is_said_to_have_been_searched_as_plain_text(tmp_path, monkeypatch):
    answer = _the_answer_to(tmp_path, monkeypatch, "list_notes(Query(", "/notes-api")

    assert "not valid" in answer and "plain text only" in answer


@pytest.mark.parametrize("pattern, path", [("^## ", "/docs"), ("^zz.*q", "/"), ("a(", "/")],
                         ids=["matched as an expression", "matched neither way", "not a valid expression"])
def test_the_notes_use_none_of_the_banned_words(tmp_path, monkeypatch, pattern, path):
    note = _the_answer_to(tmp_path, monkeypatch, pattern, path).split("\n\n")[0]

    assert "regular expression" in note
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{re.escape(word)}\b", note, re.IGNORECASE), word
