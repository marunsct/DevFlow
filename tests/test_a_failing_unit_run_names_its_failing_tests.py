"""A failing unit run names its failing tests, even when the runner prints nothing.

A runner told to write JUnit to a file prints nothing. Measured on one run:
three rounds' defects read "The unit tests fail. The runner's output ends:
(no output)", each fixer had to find out which tests failed, and the sprint
was planned again.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from app.graph.workflow import _run_unit_tests_procedurally
from app.stacks.contract import CONTRACT_FILE

REPORT = """<?xml version="1.0"?>
<testsuites><testsuite name="store">
  <testcase name="keeps a note" file="tests/store.test.ts"/>
  <testcase name="rejects an empty body" file="tests/store.test.ts">
    <failure message="Expected 400, received 500">AssertionError: Expected 400, received 500</failure>
  </testcase>
</testsuite></testsuites>
"""


def _project(root: Path) -> None:
    contract = root / CONTRACT_FILE
    contract.parent.mkdir(parents=True, exist_ok=True)
    contract.write_text(json.dumps({
        "pack": "proven-setup",
        "project": "app",
        "unit_test": ["node", "--test", "--test-reporter=junit",
                      "--test-reporter-destination=test-results/unit.xml", "tests/*.test.ts"],
    }))
    (root / "app" / "test-results").mkdir(parents=True)


def test_the_failing_tests_are_read_from_the_report(tmp_path) -> None:
    _project(tmp_path)

    def runner(command, category, project):
        (tmp_path / "app" / "test-results" / "unit.xml").write_text(REPORT)
        return {"returncode": 1, "stdout": "", "stderr": ""}

    with patch("app.stacks.scaffold.sandbox_runner", return_value=runner):
        passed, output = _run_unit_tests_procedurally(str(tmp_path))

    assert passed is False
    assert "rejects an empty body" in output and "Expected 400, received 500" in output
    assert "keeps a note" not in output


def test_a_report_from_an_earlier_run_is_not_read(tmp_path) -> None:
    _project(tmp_path)
    (tmp_path / "app" / "test-results" / "unit.xml").write_text(REPORT)

    with patch("app.stacks.scaffold.sandbox_runner",
               return_value=lambda *a: {"returncode": 1, "stdout": "boom", "stderr": ""}):
        passed, output = _run_unit_tests_procedurally(str(tmp_path))

    assert passed is False and "boom" in output and "rejects an empty body" not in output


def test_a_run_the_harness_cannot_make_says_why(tmp_path) -> None:
    _project(tmp_path)

    def runner(*_):
        raise RuntimeError("the sandbox is not available")

    with patch("app.stacks.scaffold.sandbox_runner", return_value=runner):
        passed, output = _run_unit_tests_procedurally(str(tmp_path))

    assert passed is False and "the sandbox is not available" in output


def test_a_run_the_sandbox_answers_as_text_passes(tmp_path) -> None:
    """The sandbox gives the exit code as text; every harness round had said the unit tests failed."""
    _project(tmp_path)

    with patch("app.stacks.scaffold.sandbox_runner",
               return_value=lambda *a: {"returncode": "0", "stdout": "", "stderr": ""}):
        passed, _ = _run_unit_tests_procedurally(str(tmp_path))
    with patch("app.stacks.scaffold.sandbox_runner",
               return_value=lambda *a: {"returncode": "1", "stdout": "x", "stderr": ""}):
        failed, _ = _run_unit_tests_procedurally(str(tmp_path))

    assert passed is True and failed is False
