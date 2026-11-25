"""A test run's totals are read from what its runner really printed, captured from runs (`tests/captured/`).

Deep review of the parsers (2026-11-25), finding 4: the totals the execution ledger records - the "N of M passed" a
stage is told, the sprint summary's counts, and the "the test suite has shrunk ... DO NOT remove tests" warning - were
wrong on four real shapes, each of which the hand-made fixtures did not have:

- nextest with a failure prints each failing test's captured output, libtest's "test result: FAILED. 0 passed;
  1 failed" among it, and that line was read: 44 tests, 15 failing, were recorded as 0 of 1;
- pytest's tests that errored (at setup) were not counted: "23 passed, 9 warnings, 9 errors" read as 23 of 23;
- a fullstack `npm test` runs Vitest then pytest, and only Vitest's totals were read: 53 tests read as 20, and the
  stage was warned that its suite had shrunk from 33;
- a Playwright run over a minute ends "17 passed (4.7m)", which the seconds-only form never read.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tools.sandbox import _the_counts_a_test_run_reported

CAPTURED = Path(__file__).parent / "captured"


def _printed(name: str) -> dict:
    """A command's result as the sandbox returned it (`.json`), or a runner's whole output as the journal kept it."""
    text = (CAPTURED / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else {"stdout": text}


@pytest.mark.parametrize(("captured", "expected"), [
    ("cargo-nextest-red-44-tests-15-failed.txt", {"passed": 29, "failed": 15, "tests": 44}),
    ("pytest-9.2-passed-and-setup-errors.json", {"passed": 23, "failed": 9, "tests": 32}),
    ("pytest-9.2-failed-passed-and-errors.json", {"passed": 80, "failed": 26, "tests": 106}),
    ("vitest-3.2-then-pytest-9.2-in-one-npm-test.json", {"passed": 43, "failed": 10, "tests": 53}),
    ("playwright-1.64-summary-of-a-run-over-a-minute.txt", {"passed": 17, "failed": 80, "tests": 97}),
    ("playwright-1.64-97-tests-93-failed.log", {"passed": 4, "failed": 93, "tests": 97}),
])
def test_a_runner_s_real_output_is_counted_as_it_reported(captured, expected):
    assert _the_counts_a_test_run_reported(_printed(captured)) == expected


def test_a_pytest_run_stopped_at_collection_counts_no_tests():
    """Errors that stopped collection ran no test: counted as tests, the next full run's suite would read as grown
    from one, and a suite that stops collecting as shrunk to one."""
    assert _the_counts_a_test_run_reported(_printed("pytest-9.2-stopped-at-collection.json")) == {}
