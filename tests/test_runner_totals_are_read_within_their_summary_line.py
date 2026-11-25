"""A runner's totals are read within its own summary line (launch review L1).

Read across lines, "Tests: 3 failed, 3 total" followed by "Snapshots: 2 passed" counted two passing tests, and pytest's
bare "(\\d+) passed" matched any line that said a number and "passed".
"""
from __future__ import annotations

from app.tools.sandbox import _the_counts_a_test_run_reported


def _totals(text: str) -> dict:
    return _the_counts_a_test_run_reported({"stdout": text})


def test_jest_does_not_take_the_snapshots_line_for_tests():
    text = "Tests:       3 failed, 3 total\nSnapshots:   2 passed, 2 total\nTime: 1s\n"
    assert _totals(text) == {"passed": 0, "failed": 3, "tests": 3}


def test_pytest_reads_its_summary_line_not_a_sentence_in_the_output():
    text = "note: 12 passed checks earlier in the log\n...F\n3 passed, 1 failed in 0.42s\n"
    assert _totals(text) == {"passed": 3, "failed": 1, "tests": 4}


def test_the_usual_summaries_still_read():
    assert _totals("Tests:       1 failed, 5 passed, 6 total") == {"passed": 5, "failed": 1, "tests": 6}
    assert _totals(" Tests  5 passed | 1 failed (6)")["passed"] == 5
    assert _totals("test result: FAILED. 3 passed; 1 failed;")["failed"] == 1
