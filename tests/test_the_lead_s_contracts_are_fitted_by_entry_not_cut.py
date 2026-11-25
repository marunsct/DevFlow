"""The technical lead's contracts are fitted to its request entry by entry, never cut mid-word (LF.1470).

Measured on one medium run: the section the lead's work orders copy from was cut blind - "... Implements JWT
encode/decode usin", "--- TRUNCATED (23428 chars removed for context limits) ---", "(401, "Not authenticated")" -
the contracts of the files in the middle gone with no line range to read them from. The specification, its document,
the sprint plan and the files the lead's work orders went on to own are that run's, captured from the workspace and
the transcript.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from app.agents.technical_lead import build_milestone_planning_request

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CAPTURED = json.loads((Path(__file__).parent / "captured" / "technical_lead_opening.json").read_text("utf-8"))


#: The run's document budget on its 93K slot: the blind cut kept 24,199 characters, 60% of it.
RUN_S_DOCUMENT_BUDGET = "40332"


def _contracts(tmp_path, monkeypatch) -> str:
    monkeypatch.setenv("CTX_ARCHITECT_DOCUMENT_BUDGET", RUN_S_DOCUMENT_BUDGET)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(CAPTURED["specification_document"], "utf-8")
    request = build_milestone_planning_request(
        CAPTURED["sprint_plan"], CAPTURED["sprint_goal"], str(tmp_path),
        specification=SimpleNamespace(**CAPTURED["specification"]))
    text = request["messages"][0]["content"]
    start = text.index("--- From the approved technical specification")
    return text[start:text.index("You are now planning the milestone", start)]


def test_the_section_holds_no_cut(tmp_path, monkeypatch):
    assert "--- TRUNCATED (" in CAPTURED["contracts_as_sent"]

    assert "TRUNCATED" not in _contracts(tmp_path, monkeypatch)


def test_every_file_of_the_sprint_keeps_its_contract_lines(tmp_path, monkeypatch):
    contracts = _contracts(tmp_path, monkeypatch)
    spec = CAPTURED["specification"]
    for path in CAPTURED["sprint_files"]:
        for field in ("file_plan", "function_contracts"):
            for entry in spec[field]:
                if entry.startswith(path + " ") or f"File: {path}." in entry:
                    assert f"- {entry}" in contracts, (field, path)


def test_each_section_left_short_names_its_lines(tmp_path, monkeypatch):
    contracts = _contracts(tmp_path, monkeypatch)

    short = [line for line in contracts.splitlines() if "for parts this sprint does not build" in line]
    assert short
    assert all(re.search(r"lines \d+-\d+ of /docs/technical_specification\.md", line) for line in short)


def test_within_the_budget_the_contracts_are_whole(tmp_path):
    from app.agents import contracts_fitted

    text = contracts_fitted.fitted([("File plan", ["a.py - one", "b.py - two"])], 10_000, set(), set())

    assert text == "File plan:\n- a.py - one\n- b.py - two"


def test_what_it_says_uses_none_of_the_banned_words():
    from app.agents import contracts_fitted

    text = contracts_fitted.fitted([("File plan", ["x" * 50, "y" * 50]), ("Testing", ["z" * 80])], 90, {"y"}, set())
    assert "parts this sprint does not build" in text and not BANNED.search(text.replace("x", "").replace("z", ""))
