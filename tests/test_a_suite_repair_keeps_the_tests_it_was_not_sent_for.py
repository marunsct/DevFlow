"""A suite repair keeps every test it was not sent for.

One run's repair, sent for one test that could not pass, wrote the suite's file
back with that test alone in it: seventeen criteria lost their tests, and the
suite went back to QA for all of them. The repair request said "change only the
tests named above"; the write is now held to it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.acceptance import suite
from app.tools.repository import RepositoryToolError, write_approved_artifact

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
FILE = "notes-api/acceptance/test_acceptance.py"
SUITE = "".join(f"def test_ac{i}_x(base_url):\n    assert True\n\n" for i in range(1, 19))


@pytest.fixture
def reopened(tmp_path: Path) -> Path:
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "acceptance.json").write_text(json.dumps({"project": "notes-api", "acceptance_dir": "acceptance"}))
    (tmp_path / "notes-api" / "acceptance").mkdir(parents=True)
    (tmp_path / FILE).write_text(SUITE)
    suite.lock(tmp_path)
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["test_ac18_x"])
    return tmp_path


def test_a_repair_that_drops_other_tests_is_refused_and_names_them(reopened: Path):
    with pytest.raises(RepositoryToolError) as refused:
        write_approved_artifact(reopened, FILE, "def test_ac18_x(base_url):\n    assert True\n", by_the_workflow=True)

    message = str(refused.value)
    assert "remove 17 test(s)" in message and "`test_ac10_x`" in message and "and 9 more" in message
    assert not BANNED.search(message)
    assert (reopened / FILE).read_text() == SUITE


def test_a_repair_that_changes_only_its_test_is_written(reopened: Path):
    repaired = SUITE.replace("def test_ac18_x(base_url):\n    assert True", "def test_ac18_x(base_url):\n    assert 1 == 1")

    write_approved_artifact(reopened, FILE, repaired, by_the_workflow=True)

    assert "assert 1 == 1" in (reopened / FILE).read_text()


def test_outside_a_repair_nothing_is_held(tmp_path: Path):
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "acceptance.json").write_text(json.dumps({"project": "notes-api", "acceptance_dir": "acceptance"}))
    (tmp_path / "notes-api" / "acceptance").mkdir(parents=True)
    (tmp_path / FILE).write_text(SUITE)

    write_approved_artifact(tmp_path, FILE, "def test_ac1_x(base_url):\n    assert True\n", by_the_workflow=True)

    assert suite.tests_a_repair_would_drop(tmp_path, FILE, "") == []


def test_locking_again_ends_the_repair(reopened: Path):
    suite.lock(reopened)

    assert "repairing" not in json.loads((reopened / ".harness" / "acceptance.json").read_text())
