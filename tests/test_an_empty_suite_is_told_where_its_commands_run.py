"""A suite whose runner collected nothing is told the folder its commands run in and what the runner could not find.

Measured on one run: two commands named `test_api.py` and `test_ui.py` while both sat in the suite's folder; pytest
said "file or directory not found", and two rounds were told only that zero tests ran.
"""
from __future__ import annotations

import json
import re

from app.acceptance import junit, suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SAID = ("collecting ... collected 0 items\n"
        "============================ no tests ran in 0.00s =============================\n"
        "\x1b[31mERROR: file or directory not found: test_ui.py\x1b[0m\n")


def _empty(tmp_path, output):
    (tmp_path / "bookmarks" / "acceptance").mkdir(parents=True)
    (tmp_path / "bookmarks" / "acceptance" / "run.json").write_text(json.dumps({"command": ["run"], "report": "r.xml"}))
    (tmp_path / ".project-directory").write_text("bookmarks\n")
    result = suite.AcceptanceResult(ran=True, exit_code=4, command="python -m pytest test_ui.py",
                                    report=junit.Report(tests=[], found=True), output=output)
    [said] = suite.vacuous_green(tmp_path, result)
    return said


def test_it_is_told_where_the_commands_run_and_what_the_runner_could_not_find(tmp_path):
    said = _empty(tmp_path, SAID)
    assert "runs in `bookmarks/`" in said and "`acceptance/<file>`" in said
    assert "file or directory not found: test_ui.py" in said and "\x1b" not in said
    assert not BANNED.search(said)


def test_a_runner_that_said_nothing_of_the_kind_adds_only_the_folder(tmp_path):
    said = _empty(tmp_path, "collected 0 items\n")
    assert "runs in `bookmarks/`" in said and "The runner said" not in said
