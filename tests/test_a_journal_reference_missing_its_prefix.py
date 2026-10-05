"""A journal reference copied without its timestamp prefix is still read.

An entry is named `<timestamp>-<run>-<role>-<program>-<stream>-<random>.log`.
One run's `specialist_testing_3` asked six times for
`run-<id>-ui_ux_specialist-node-stderr-<random>.log`; the reply listed
the one entry, `<timestamp>-run-<id>-...-<random>.log`, and from the third
ask said "a reference that does not resolve never will".
"""

from __future__ import annotations

import pytest

from app.tools import journal


@pytest.fixture
def a_run(tmp_path, monkeypatch):
    monkeypatch.setenv("CTX_JOURNAL_ROOT", str(tmp_path / "journal"))
    root = tmp_path / "workspace-run-aaaaaaa1-1111-2222"
    root.mkdir()
    return root


def _tool(root):
    from app.tools.agent_toolkit import build_journal_read_tool

    return build_journal_read_tool(str(root))


def _without_prefix(reference: str) -> str:
    return reference.split("-", 1)[1]


def test_the_entry_is_read(a_run):
    real = journal.write_entry("ui_ux_specialist-node-stderr", "Error: boom\n", scope="run-aaaaaaa1")

    result = _tool(a_run).invoke({"reference": _without_prefix(real)})

    assert "Error: boom" in result


def test_search_still_applies(a_run):
    real = journal.write_entry("ui_ux_specialist-node-stderr", "one\nError: boom\nthree\n", scope="run-aaaaaaa1")

    result = _tool(a_run).invoke({"reference": _without_prefix(real), "search": "boom"})

    assert "Error: boom" in result
    assert "three" not in result


def test_two_candidates_are_not_chosen_between():
    from app.tools import agent_toolkit

    entries = ["1-x-stderr-abcdef12.log", "2-x-stderr-abcdef12.log"]

    assert agent_toolkit._the_one_entry_it_meant("x-stderr-abcdef12.log", entries) == ""


def test_a_short_fragment_is_not_resolved(a_run):
    journal.write_entry("ui_ux_specialist-node-stderr", "x\n", scope="run-aaaaaaa1")

    result = _tool(a_run).invoke({"reference": ".log"})

    assert isinstance(result, dict) and "error" in result


def test_a_reference_missing_its_extension_is_read(a_run):
    """One run's QA asked twice for the whole name but its `.log`, and was refused."""
    real = journal.write_entry("testing_specialist-npm-stdout", "Error: boom\n", scope="run-aaaaaaa1")

    result = _tool(a_run).invoke({"reference": real.removesuffix(".log")})

    assert "Error: boom" in result


def test_a_reference_missing_both_prefix_and_extension_is_read(a_run):
    real = journal.write_entry("testing_specialist-npm-stdout", "Error: boom\n", scope="run-aaaaaaa1")

    result = _tool(a_run).invoke({"reference": _without_prefix(real).removesuffix(".log")})

    assert "Error: boom" in result
