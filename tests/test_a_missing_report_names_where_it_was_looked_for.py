"""A suite whose report is missing is told where the harness looked and which reports the run did write.

Measured on a suite with two runners under one script: the second runner emptied its output folder, deleting the
first runner's report, and the author, told only that no report was written while its own run passed, spent its last
round without a lead.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.acceptance import suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
JUNIT = '<testsuite name="s" tests="1"><testcase name="t" classname="c"/></testsuite>'


def _a_suite(root: Path, report: str = "out/first.xml") -> Path:
    project = root / "app"
    (project / "acceptance").mkdir(parents=True)
    (project / "acceptance" / "run.json").write_text(json.dumps({"command": ["run"], "report": report}))
    (root / ".project-directory").write_text("app\n")
    return project


def _run(root: Path, write) -> suite.AcceptanceResult:
    def runner(argv, category, project):
        write()
        return {"returncode": "0", "stdout": "generated xml file: out/first.xml"}

    return suite.run(root, runner=runner, save=False)


def test_it_names_the_path_looked_for_and_a_report_the_run_did_write(tmp_path):
    project = _a_suite(tmp_path)

    def write():
        (project / "acceptance" / "out").mkdir(parents=True)
        (project / "acceptance" / "out" / "second.xml").write_text(JUNIT)

    result = _run(tmp_path, write)

    assert not result.ran
    assert "the runner wrote no report" in result.problem
    assert "`out/first.xml`" in result.problem
    assert "`acceptance/out/second.xml`" in result.problem
    assert "empties its output folder" in result.problem
    assert not BANNED.search(result.problem)


def test_a_report_older_than_the_run_and_files_of_other_kinds_are_not_named(tmp_path):
    project = _a_suite(tmp_path)
    (project / "old.xml").write_text(JUNIT)
    import os

    os.utime(project / "old.xml", (1, 1))

    def write():
        (project / "page.xml").write_text("<html/>")
        (project / "node_modules" / "x").mkdir(parents=True)
        (project / "node_modules" / "x" / "fresh.xml").write_text(JUNIT)

    result = _run(tmp_path, write)

    assert "the runner wrote no report" in result.problem and "`out/first.xml`" in result.problem
    assert "old.xml" not in result.problem and "page.xml" not in result.problem and "fresh.xml" not in result.problem
