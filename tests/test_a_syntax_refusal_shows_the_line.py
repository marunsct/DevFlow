"""The parse refusal named a line number and never showed the line.

Measured on run 1c9854c7's `test_round_0`: an `edit_artifact` refused with
"Node cannot parse this file on line 26: SyntaxError: Unexpected token '}'",
sent again unchanged, and again, and again - four attempts, the last two
answered only by the repeat guard, before the stage gave up and rewrote the
whole file instead.

The agent had the number and not the text, and the text is what it was about to
rewrite. `Refusing to write ... Node cannot parse this file` is the largest
single refusal category in the stored transcripts, at 45 occurrences.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.javascript_parse import CONTEXT_LINES, parse_error

UNBALANCED = """// app
const KEY = "tasks";

function loadTasks() {
  return [];
}

function addTask(t) {
  const tasks = loadTasks();
  tasks.push(t);
  return tasks;
}
}
"""


@pytest.fixture
def where(tmp_path: Path) -> Path:
    return tmp_path / "app.js"


def _note(where: Path, content: str) -> str:
    note = parse_error(where, content)
    if note is None:
        pytest.skip("node --check is not available in this environment")
    return note


def test_the_offending_line_is_quoted(where: Path):
    note = _note(where, UNBALANCED)

    assert "This is what you sent, around that line" in note
    assert "> " in note


def test_the_line_numbers_match_the_error(where: Path):
    """The content being refused is numbered, not the file on disk."""
    note = _note(where, UNBALANCED)

    assert "on line 13" in note
    assert "13 | }" in note


def test_the_neighbours_are_shown(where: Path):
    note = _note(where, UNBALANCED)

    assert "return tasks;" in note
    assert f"{13 - CONTEXT_LINES}" in note or "9 |" in note


def test_a_file_that_parses_says_nothing(where: Path):
    assert parse_error(where, "const a = 1;\nfunction b() { return a; }\n") is None


def test_the_existing_explanation_survives(where: Path):
    """The bracket-balance half was already there and must not be displaced."""
    note = _note(where, UNBALANCED)

    assert "The brackets do not balance" in note
    assert "node --check" in note


def test_a_failure_with_no_line_number_still_returns_a_message(where: Path):
    """The quote is an addition; its absence must not remove the refusal."""
    from app.analysis.javascript_parse import _around_the_failure

    assert _around_the_failure(None, UNBALANCED) == ""
    assert _around_the_failure("999", UNBALANCED) == ""
    assert _around_the_failure("not-a-number", UNBALANCED) == ""
