"""A journal search that finds nothing is the answer, not a tool failure.

A test round searched a passing log for `not ok|Error|FAIL|AssertionError|...`.
The search is literal, so the alternation matched nothing, and the result was
`{"error": ...}`. The model then spent a second call searching for `not ok`
alone, to be sure of an absence it had already been told about.
"""
from __future__ import annotations

import pytest

_LOG = "# tests 3\nok 1 - adds\nok 2 - deletes\nnot ok 3 - edits\n# fail 1\n"
_REF = "1790740924-run-x-npm-stdout-395d6827.log"


@pytest.fixture
def tool(tmp_path, monkeypatch):
    from app.tools import agent_toolkit, journal

    monkeypatch.setattr(journal, "read_entry", lambda name: _LOG if name == _REF else None)
    return agent_toolkit.build_journal_read_tool(str(tmp_path))


def test_nothing_found_is_not_an_error(tool):
    result = tool.invoke({"reference": _REF, "search": "SyntaxError"})

    assert isinstance(result, str)
    assert "No line of" in result and "'SyntaxError'" in result
    assert "the output does not contain it" in result


def test_an_alternation_is_searched_per_alternative(tool):
    result = tool.invoke({"reference": _REF, "search": "not ok|SyntaxError|FAIL"})

    assert "3: not ok 3 - edits" in result


def test_an_alternation_that_finds_nothing_names_each_alternative(tool):
    result = tool.invoke({"reference": _REF, "search": "SyntaxError|TypeError"})

    assert isinstance(result, str)
    assert "none of 'SyntaxError', 'TypeError'" in result


def test_text_that_really_contains_a_bar_matches_itself_first(tool, monkeypatch):
    from app.tools import journal

    monkeypatch.setattr(journal, "read_entry", lambda name: "a | b\nb only\n")
    result = tool.invoke({"reference": _REF, "search": "a | b"})

    assert "0: a | b" in result
    assert "b only" not in result


def test_a_double_bar_is_code_not_alternation():
    from app.tools.agent_toolkit import _the_alternatives_meant

    assert _the_alternatives_meant("a || b") == []
    assert _the_alternatives_meant("ok|fail") == ["ok", "fail"]
    assert _the_alternatives_meant("plain") == []
