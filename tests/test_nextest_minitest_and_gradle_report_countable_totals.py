"""The Rust packs' nextest, the Rails pack's minitest and Gradle print totals the ledger now counts.

Deep review 2026-11-18, item E3: the totals a test command printed were read for TAP, jest, vitest, pytest,
Playwright, cargo's own runner, go, Maven, .NET, RSpec, PHPUnit and gotestsum - not for `cargo nextest`, which every
Rust pack runs, nor minitest (`rails test`), nor Gradle. With no counts in the ledger the check that a suite which
was passing has stopped cannot fire.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import _the_counts_a_test_run_reported

OUTPUT = {
    "nextest": (
        "    Starting 4 tests across 1 binary\n"
        "        PASS [   0.003s] notes::tests::creates\n"
        "        FAIL [   0.004s] notes::tests::rejects\n"
        "     Summary [   0.012s] 4 tests run: 3 passed, 1 failed, 0 skipped\n"
    ),
    "minitest": (
        "Run options: --seed 4242\n\n# Running:\n\n..FE.\n\n"
        "Finished in 0.012s, 416.6 runs/s.\n\n5 runs, 9 assertions, 1 failures, 1 errors, 0 skips\n"
    ),
    "gradle": "> Task :test FAILED\n\n5 tests completed, 1 failed, 1 skipped\n\nFAILURE: Build failed with an exception.\n",
}
EXPECTED = {
    "nextest": {"passed": 3, "failed": 1, "tests": 4},
    "minitest": {"passed": 3, "failed": 2, "tests": 5},
    "gradle": {"passed": 3, "failed": 1, "tests": 4},
}


@pytest.mark.parametrize("runner", sorted(OUTPUT))
def test_a_runner_s_printed_totals_are_counted(runner):
    assert _the_counts_a_test_run_reported({"stdout": OUTPUT[runner]}) == EXPECTED[runner]


def test_a_green_nextest_run_counts_its_passes():
    counts = _the_counts_a_test_run_reported(
        {"stderr": "     Summary [   0.020s] 7 tests run: 7 passed, 0 skipped\n"})

    assert counts == {"passed": 7, "failed": 0, "tests": 7}
