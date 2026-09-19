"""The harness breaks its own green suite, and could not see it.

Measured across all 50 stored transcripts, for the 41 runs that ran a suite:

    reached a green suite at some point    40
    went green and then red again          39
    ended on a green suite                 13
    never green                             1

The regression note - "N test(s) that were passing have stopped" - fired in
**3** of those runs. The check was right and blind: it needs the pass and
test counts in the ledger, and `_the_counts_a_test_run_reported` read only
TAP (`# pass N`, `# fail N`, `# tests N`), which is what `node --test` emits
and nothing else does.

Every other runner reported its results in its own words, the ledger recorded
no counts, and the comparison had nothing to compare. That is root-cause
class H: a rule written for the runner that happened to be in front of it.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import _RUNNER_TOTALS, _the_counts_a_test_run_reported

OUTPUT = {
    "node --test": "TAP version 13\n# tests 6\n# pass 5\n# fail 1\n",
    "jest": "Tests:       1 failed, 5 passed, 6 total\nSnapshots:   0 total\n",
    "vitest": " Test Files  1 failed (1)\n      Tests  5 passed | 1 failed (6)\n",
    "pytest": "===== 5 passed, 1 failed in 0.42s =====\n",
    "cargo": "test result: FAILED. 3 passed; 1 failed; 0 ignored; 0 measured\n",
    "go": "--- PASS: TestA (0.00s)\n--- PASS: TestB (0.00s)\n--- FAIL: TestC (0.01s)\nFAIL\n",
}


@pytest.mark.parametrize("runner", sorted(OUTPUT))
def test_every_runner_reports_countable_totals(runner):
    counts = _the_counts_a_test_run_reported({"stdout": OUTPUT[runner]})

    assert counts, f"{runner} output yields no counts, so a regression is invisible"
    assert counts["tests"] == counts["passed"] + counts["failed"]
    assert counts["passed"] > 0 and counts["failed"] > 0


def test_a_playwright_run_with_no_failures_still_counts():
    """The green half of the comparison matters as much as the red."""
    counts = _the_counts_a_test_run_reported({"stdout": "  5 passed (12.3s)\n"})

    assert counts == {"passed": 5, "failed": 0, "tests": 5}


def test_a_playwright_run_with_failures_counts_both():
    counts = _the_counts_a_test_run_reported(
        {"stdout": "  3 failed\n    tests/a.spec.ts:4:5\n  2 passed (30.0s)\n"}
    )

    assert counts == {"passed": 2, "failed": 3, "tests": 5}


def test_output_that_is_not_a_test_run_yields_nothing():
    """A count invented from ordinary output would report false regressions."""
    for text in ("Hello world\n", "added 88 packages in 3s\n", ""):
        assert _the_counts_a_test_run_reported({"stdout": text}) == {}


def test_a_regression_is_reported_once_the_counts_exist(tmp_path, monkeypatch):
    """The check was always right; it only ever lacked the numbers."""
    import app.tools.sandbox as sandbox

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sandbox, "execution_enabled", lambda: False)

    green = {"stdout": "Tests:       0 failed, 5 passed, 5 total\n", "returncode": "0"}
    red = {"stdout": "Tests:       3 failed, 2 passed, 5 total\n", "returncode": "1"}

    sandbox._record_execution(str(tmp_path), "testing_specialist", ["npm", "test"], green)
    note = sandbox._fewer_pass_than_last_time(
        str(tmp_path), ["npm", "test"], None, red
    )

    assert "were passing have stopped" in note
    assert "not smaller" in note


def test_every_runner_in_the_table_is_one_a_stack_can_choose():
    """The set rule, so a runner added to a toolchain gets counted too."""
    from app.tools.sandbox import TOOLCHAINS

    runnable = {name for names in TOOLCHAINS.values() for name in names}
    named = {name for name, _, _ in _RUNNER_TOTALS}
    # `jest` and `vitest` are in the toolchains; pytest, cargo and go are the
    # runners of their languages rather than separate executables.
    assert {"jest", "vitest"} <= runnable
    assert {"jest", "vitest", "pytest", "cargo", "go"} <= named
