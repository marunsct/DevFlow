"""A suite writer refused a write to the product is told what to do with a test the product fails (2026-11-09).

On a reopened suite the product already exists; the refusal said it was "built after this suite is locked" and
nothing more, and one run's writers tried to write the product 14 times (50 refusals across 15 of 60 runs).
"""
from __future__ import annotations

import re

from app.tools import repository

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_refusal_says_a_test_the_product_fails_stays_failing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.acceptance.suite.relative_directory", lambda root: "notes-api/acceptance")
    monkeypatch.setattr("app.acceptance.suite.is_locked", lambda root: False, raising=False)
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda default="": "acceptance_author_1")
    target = tmp_path / "notes-api" / "notes_api" / "main.py"
    target.parent.mkdir(parents=True)

    said = repository._the_harness_s_own_or_the_locked_suite(tmp_path, target)

    assert said and "leave it failing for them" in said
    assert "after this suite is locked" not in said
    assert not BANNED.search(said.split("'", 2)[-1])
