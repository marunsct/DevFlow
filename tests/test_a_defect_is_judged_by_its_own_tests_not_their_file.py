"""A defect's check is judged by the tests that carry its criterion, not by the exit of the file they share.

A file holds tests of several criteria. Measured on a gate run: AC-9's six
tests passed, the file also held a later sprint's AC-8 test that failed, and
AC-9 was left open every time its fix was measured.
"""
from __future__ import annotations

from pathlib import Path

from app.acceptance import per_file

REPORT = """<?xml version="1.0"?><testsuites><testsuite name="pytest">
<testcase classname="acceptance.test_ac1_ac9" name="test_ac9_duplicate_username_returns_409"/>
<testcase classname="acceptance.test_ac1_ac9" name="test_ac9_empty_username_returns_422"/>
<testcase classname="acceptance.test_ac1_ac9" name="test_ac8_item_shape_and_monotonic_ids"><failure message="assert 1 == 2">x</failure></testcase>
</testsuite></testsuites>"""
RECORD = {"project": "items-api", "acceptance_dir": "acceptance", "acceptance_pattern": "test_*.py",
          "acceptance_report": "test-results/acceptance.xml",
          "acceptance_test": [".venv/bin/python", "-m", "pytest", "acceptance", "-q", "--junitxml=test-results/acceptance.xml"]}


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "items-api" / "acceptance").mkdir(parents=True)
    (tmp_path / "items-api" / "acceptance" / "test_ac1_ac9.py").write_text("def test_ac9_x(): pass  # AC-1, AC-9, AC-8\n")
    return tmp_path


def _a_run_that_writes(report: str):
    def run(argv, category, project):
        path = Path(run.root) / "items-api" / "test-results" / "acceptance.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report)
        return {"returncode": "1", "stdout": "1 failed, 2 passed"}
    return run


def test_the_criterion_s_own_tests_passing_finish_the_file_for_it(tmp_path):
    root = _workspace(tmp_path)
    run = _a_run_that_writes(REPORT)
    run.root = root

    assert [r["outcome"] for r in per_file.each_file(root, RECORD, run, naming={"AC-9"})] == ["finished"]
    assert [r["outcome"] for r in per_file.each_file(root, RECORD, run, naming={"AC-8"})] == ["failed"]


def test_a_file_whose_tests_carry_no_named_criterion_keeps_its_exit_code(tmp_path):
    root = _workspace(tmp_path)
    run = _a_run_that_writes(REPORT)
    run.root = root

    assert [r["outcome"] for r in per_file.each_file(root, RECORD, run, naming={"AC-1"})] == ["failed"]
    assert [r["outcome"] for r in per_file.each_file(root, RECORD, run)] == ["failed"]
