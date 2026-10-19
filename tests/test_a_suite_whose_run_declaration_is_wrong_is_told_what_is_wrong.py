"""A suite's `run.json` in the wrong shape is refused, and named, with the shape it needs (measured live).

A run whose setup was left to the agents declared its suite's runners in
`acceptance/run.json` as a `commands` list of two with a report directory. The
harness read no command and sent QA back twice with "no command is known for
this suite" - nothing it could act on.
"""
from __future__ import annotations

import json
import re

import pytest

from app.acceptance import suite
from app.tools import repository

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

WRONG = {
    "commands": [{"name": "api", "command": ["python", "-m", "pytest", "acceptance"]},
                 {"name": "e2e", "command": ["npx", "playwright", "test"]}],
    "report": "acceptance/report/",
}


def _project(tmp_path):
    (tmp_path / ".project-directory").write_text("bookmarks\n")
    (tmp_path / "bookmarks" / "acceptance").mkdir(parents=True)
    return tmp_path


def test_the_send_back_names_what_is_wrong(tmp_path):
    root = _project(tmp_path)
    (root / "bookmarks" / "acceptance" / "run.json").write_text(json.dumps(WRONG))

    result = suite.run(root, runner=lambda argv, category, where: {"returncode": "0"}, save=False)

    assert not result.ran
    assert "not a `commands` list" in result.problem and "one JUnit XML file" in result.problem
    assert '{"command": [' in result.problem
    assert not BANNED.search(result.problem)


def test_a_missing_declaration_says_it_is_missing(tmp_path):
    result = suite.run(_project(tmp_path), runner=lambda argv, category, where: {"returncode": "0"}, save=False)

    assert "`bookmarks/acceptance/run.json` is not written" in result.problem


def test_the_wrong_shape_is_refused_as_it_is_written(tmp_path):
    root = _project(tmp_path)

    with pytest.raises(repository.RepositoryToolError) as refused:
        repository.write_approved_artifact(root, "bookmarks/acceptance/run.json", json.dumps(WRONG))

    assert "not a `commands` list" in str(refused.value)
    assert not (root / "bookmarks" / "acceptance" / "run.json").exists()


def test_the_right_shape_is_written(tmp_path):
    root = _project(tmp_path)
    good = {"command": ["python", "acceptance/run_all.py"], "report": "acceptance/report/all.xml"}

    repository.write_approved_artifact(root, "bookmarks/acceptance/run.json", json.dumps(good))

    assert json.loads((root / "bookmarks" / "acceptance" / "run.json").read_text()) == good
