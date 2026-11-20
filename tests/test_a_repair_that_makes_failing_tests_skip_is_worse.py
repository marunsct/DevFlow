"""A repair that turns failing tests into skipped ones has made the suite worse, and is never kept as its best version.

Found in the suite-repair design review: the suite before a repair was counted without its skipped tests and each
repaired version with them, so a repair that made its failing tests skip read as running as many tests as before.
"""
from __future__ import annotations

import json

from app.acceptance import junit, suite

LOCKED = "test('[AC-1] a', async () => { expect(1).toBe(2); });\ntest('[AC-2] b', async () => {});\n" \
         "test('[AC-3] c', async () => {});\n"
SKIPPING = LOCKED.replace("test('[AC-1] a'", "test.skip('[AC-1] a'")


def _reopened(tmp_path):
    """The suite locked, measured 2 passing and 1 failing, reopened for `[AC-1] a`, and changed to skip it."""
    (tmp_path / ".project-directory").write_text("notes\n")
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text(LOCKED)
    suite.lock(tmp_path)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps({"ran": True, "passed": 2, "failed": 1, "skipped": 0}))
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["[AC-1] a"])
    spec.write_text(SKIPPING)


SKIPPED_ONE = suite.AcceptanceResult(ran=True, report=junit.Report(found=True, tests=[
    junit.TestResult(name="[AC-1] a", outcome="skipped"),
    junit.TestResult(name="[AC-2] b", outcome="passed"),
    junit.TestResult(name="[AC-3] c", outcome="passed")]))


def test_a_repair_that_makes_a_failing_test_skip_is_worse_than_before(tmp_path):
    _reopened(tmp_path)

    told = suite.a_repair_that_made_it_worse(tmp_path, SKIPPED_ONE)

    assert "now runs 2 test(s) and 2 pass" in told and "ran 3 and 2 passed" in told


def test_a_version_that_skips_a_failing_test_is_never_kept_as_the_best(tmp_path):
    _reopened(tmp_path)

    assert suite.keep_the_best_of_the_repair(tmp_path, SKIPPED_ONE) is False
