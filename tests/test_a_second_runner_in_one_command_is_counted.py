"""A command that runs two test runners is counted as both.

`node --test app.test.mjs && playwright test` is one command and two runners.
The counts stopped at the TAP totals, so one run's sprint summary reported
"Test Cases: 36" for a suite of 36 unit tests and 10 browser tests.
"""

from __future__ import annotations

from app.tools.sandbox import _the_counts_a_test_run_reported

TAP = "TAP version 13\nok 1 - generateId\n1..36\n# tests 36\n# suites 8\n# pass 36\n# fail 0\n"
PLAYWRIGHT = "\nRunning 10 tests using 1 worker\n  10 passed (4.6s)\n"
PLAYWRIGHT_RED = "\nRunning 10 tests using 1 worker\n  2 failed\n  8 passed (6.1s)\n"


def test_both_runners_are_counted():
    assert _the_counts_a_test_run_reported({"stdout": TAP + PLAYWRIGHT}) == {
        "passed": 46, "failed": 0, "tests": 46,
    }


def test_a_failure_in_the_second_runner_is_counted():
    counts = _the_counts_a_test_run_reported({"stdout": TAP + PLAYWRIGHT_RED})

    assert counts == {"passed": 44, "failed": 2, "tests": 46}


def test_tap_alone_is_unchanged():
    assert _the_counts_a_test_run_reported({"stdout": TAP}) == {
        "passed": 36, "failed": 0, "tests": 36,
    }


def test_another_runner_alone_is_unchanged():
    assert _the_counts_a_test_run_reported({"stdout": PLAYWRIGHT}) == {
        "passed": 10, "failed": 0, "tests": 10,
    }
