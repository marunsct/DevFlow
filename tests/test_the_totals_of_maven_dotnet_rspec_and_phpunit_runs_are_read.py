"""The totals of a Maven, .NET, RSpec or PHPUnit test run are read, as those of the runners read before them.

Measured by the rule-coverage counter (LR.46) across the language sweep: `mvn` and `dotnet test` runs printed their
totals in forms no reader knew, so their ledger entries held no counts - the check that a suite passes fewer tests
than last time, and the sprint summary's totals, could not see those products. The summary lines below are copied
from runs' own transcripts.
"""

from __future__ import annotations

import pytest

from app.tools import sandbox


def _totals(text: str) -> dict:
    return sandbox._the_counts_a_test_run_reported({"stdout": text, "stderr": ""})


@pytest.mark.parametrize("text, passed, failed", [
    # Maven: one line per class, then the run's own line under "Results:"; errors are failures too.
    ("[INFO] Tests run: 9, Failures: 1, Errors: 0, Skipped: 0, Time elapsed: 3.2 s <<< FAILURE! -- in app.notes.NoteTest\n"
     "[INFO] Tests run: 8, Failures: 2, Errors: 0, Skipped: 0, Time elapsed: 1.1 s -- in app.notes.OtherTest\n"
     "[ERROR] Tests run: 17, Failures: 3, Errors: 0, Skipped: 0\n", 14, 3),
    ("[ERROR] Tests run: 17, Failures: 0, Errors: 17, Skipped: 0\n", 0, 17),
    ("[INFO] Tests run: 5, Failures: 1, Errors: 1, Skipped: 1\n", 2, 2),
    # Maven quiet, with only the lines per class: their sum.
    ("Tests run: 3, Failures: 1, Errors: 0, Skipped: 0, Time elapsed: 0.2 s -- in a.ATest\n"
     "Tests run: 2, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.1 s -- in a.BTest\n", 4, 1),
    # .NET: one line per test project, summed.
    ("Failed!  - Failed:    12, Passed:    13, Skipped:     0, Total:    25, Duration: 261 ms - UnitTests.dll (net8.0)\n", 13, 12),
    ("Passed!  - Failed:     0, Passed:     5, Skipped:     0, Total:     5, Duration: 1 s - A.dll (net8.0)\n"
     "Failed!  - Failed:     1, Passed:     3, Skipped:     0, Total:     4, Duration: 1 s - B.dll (net8.0)\n", 8, 1),
    # RSpec: examples less failures and pending; an error outside the examples is a failure.
    ("23 examples, 14 failures\n", 9, 14),
    ("8 examples, 0 failures, 2 pending\n", 6, 0),
    ("0 examples, 0 failures, 1 error occurred outside of examples\n", 0, 1),
    # PHPUnit: "OK (n tests, ...)" when all pass, else the counts line.
    ("OK (48 tests, 90 assertions)\n", 48, 0),
    ("OK (1 test, 1 assertion)\n", 1, 0),
    ("Tests: 1, Assertions: 1, Failures: 1.\n", 0, 1),
    ("Tests: 10, Assertions: 20, Errors: 1, Failures: 2, Skipped: 1, Incomplete: 1.\n", 5, 3),
])
def test_each_runner_s_summary_is_read(text, passed, failed):
    assert _totals(text) == {"passed": passed, "failed": failed, "tests": passed + failed}


def test_the_readers_before_them_read_as_they_did():
    assert _totals("Tests:       1 failed, 5 passed, 6 total\n") == {"passed": 5, "failed": 1, "tests": 6}
    assert _totals("===== 5 passed, 1 failed in 0.12s =====\n") == {"passed": 5, "failed": 1, "tests": 6}
    assert _totals("BUILD SUCCESS\n") == {}


def test_the_note_of_a_run_not_read_names_every_runner_read(monkeypatch):
    said = []
    from app.observability import rule_coverage

    monkeypatch.setattr(rule_coverage, "could_not_apply", lambda rule, text: said.append(text))
    sandbox._count_a_test_run_whose_totals_were_not_read(["zig", "build", "test"], {"stdout": "All 3 tests passed."})
    assert said and all(name in said[0] for name in ("maven", "dotnet", "rspec", "phpunit"))
    assert all(name in rule_coverage.CHECKS[rule_coverage.RUNNER_TOTALS] for name in ("Maven", ".NET", "RSpec", "PHPUnit"))
