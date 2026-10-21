"""A stage refused writes outside its own files is told, from the third, to stop - whatever the file or tool.

One run's acceptance writer, refused product code, tried `database.py`, then
`models.py` four times, then `main.py` by another path and through another tool
- fourteen calls, each a different file or tool, so the count kept per file
never reached its threshold and no refusal said how many there had been.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents import stage_memory
from app.tools import repository


@pytest.fixture
def acceptance_writer(tmp_path: Path, monkeypatch):
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "acceptance.json").write_text(json.dumps({"project": "notes-api", "acceptance_dir": "acceptance"}))
    (tmp_path / "notes-api" / "acceptance").mkdir(parents=True)
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: "acceptance_author_0")
    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: "run-x/acceptance_author_0/visit-1")
    return tmp_path


def _refused(root: Path, relative: str) -> str:
    return repository._the_harness_s_own_or_the_locked_suite(root, root / relative) or ""


def test_the_third_refusal_counts_them_whatever_the_file(acceptance_writer):
    first = _refused(acceptance_writer, "notes-api/notes_api/database.py")
    second = _refused(acceptance_writer, "notes-api/notes_api/models.py")
    third = _refused(acceptance_writer, "notes-api/notes_api/main.py")

    assert "not part of the acceptance suite" in first and "now been refused" not in first + second
    assert third.startswith("This stage has now been refused 3 writes outside its own files")
    assert "return your structured response" in third


def test_the_count_is_the_stage_s_own(acceptance_writer, monkeypatch):
    for name in ("a.py", "b.py", "c.py"):
        _refused(acceptance_writer, f"notes-api/notes_api/{name}")
    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: "run-x/acceptance_author_0/visit-2")

    assert "now been refused" not in _refused(acceptance_writer, "notes-api/notes_api/d.py")


def test_the_lead_uses_none_of_the_banned_words(acceptance_writer):
    import re

    for name in ("a.py", "b.py", "c.py"):
        last = _refused(acceptance_writer, f"notes-api/notes_api/{name}")
    lead = last.split("'notes-api")[0]
    assert not re.search(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", lead, re.I)
