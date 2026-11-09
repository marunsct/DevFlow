"""The refusal to change kept runner configuration names both test commands and the right way to leave a test out (2026-11-09).

A stage that wanted the unit run to skip a folder edited the kept `pytest.ini` eight times; each refusal told it to
run the acceptance suite, which it was not running, and said nothing of what to do instead.
"""
from __future__ import annotations

import re

from app.tools import repository

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_refusal_names_the_unit_and_the_acceptance_commands(tmp_path, monkeypatch) -> None:
    from app.stacks import contract

    monkeypatch.setattr(contract, "owned_by_the_harness", lambda root, path: contract.KEPT_SETUP)
    monkeypatch.setattr(contract, "released_because_it_fails", lambda root, path: False)
    monkeypatch.setattr(contract, "read", lambda root: {
        "project": "bookmarks", "unit_test": [".venv/bin/python", "-m", "pytest", "tests"],
        "acceptance_test": ["npm", "run", "test:acceptance"]})

    said = repository._a_file_the_harness_keeps(tmp_path, "bookmarks/pytest.ini")

    assert "`.venv/bin/python -m pytest tests`" in said and "`npm run test:acceptance`" in said
    assert "never by changing which tests the runner collects" in said
    assert not BANNED.search(said)
