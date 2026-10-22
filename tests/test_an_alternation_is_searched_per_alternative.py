"""A literal miss on `a|b` is searched as `a` and `b`.

`grep` is literal. One run's `test_round_0` sent `editBtn|edit-btn|editing`,
`taskList.addEventListener|deleteBtn|editBtn` and their like a dozen times, each
answered "No matches found" with advice to search per alternative.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.workspace_backend import WorkspaceBackend


@pytest.fixture
def backend(tmp_path: Path) -> WorkspaceBackend:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "app.js").write_text(
        "const deleteBtn = 1;\ntaskList.addEventListener('click', f);\nif (a || b) {}\n",
        encoding="utf-8",
    )
    return WorkspaceBackend(root_dir=str(tmp_path), virtual_mode=True)


def _lines(result) -> list[str]:
    return sorted(m["text"] if isinstance(m, dict) else str(m) for m in result.matches or [])


def test_each_alternative_is_searched(backend):
    result = backend.grep("taskList.addEventListener|deleteBtn|editBtn", "/app")

    lines = _lines(result)
    assert any("deleteBtn" in line for line in lines)
    assert any("addEventListener" in line for line in lines)


def test_nothing_found_stays_nothing(backend):
    result = backend.grep("editBtn|edit-btn", "/app")

    assert not result.matches


def test_a_pattern_that_matches_literally_is_not_split(backend):
    """`||` is code: searched as written, and found."""
    result = backend.grep("a || b", "/app")

    assert len(result.matches) == 1


def test_a_line_is_reported_once(backend):
    result = backend.grep("deleteBtn|const deleteBtn", "/app")

    assert len(result.matches) == 1
