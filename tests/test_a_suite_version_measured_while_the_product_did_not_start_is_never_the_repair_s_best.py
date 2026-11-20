"""A version of a suite under repair measured while the product did not start is never kept as the repair's best.

Measured on one run: a suite reopened while the product did not start measured 0 of 62 before the repair, so every
version that still ran 62 tests read as "no worse" - nothing measured the repair, and any version could come back as
its best. The suite-repair design review asked that such a version never be the best; the lock still can be.
"""
from __future__ import annotations

import json

from app.acceptance import junit, suite

HEAD = "const { test, expect } = require('@playwright/test');\n"
LOCKED = HEAD + "test('[AC-1] a', async () => { expect(1).toBe(2); });\ntest('[AC-2] b', async () => {});\n"
REPAIRED = LOCKED.replace("expect(1).toBe(2)", "expect(1).toBe(1)")
FAILED_ON_SETUP = "Failed: The service did not start: Traceback (most recent call last): NameError: name 'db' is not defined"


def _reopened_while_the_product_does_not_start(tmp_path):
    (tmp_path / ".project-directory").write_text("notes\n")
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text(LOCKED)
    suite.lock(tmp_path)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps({"ran": True, "passed": 0, "failed": 2}))
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["[AC-1] a"])
    spec.write_text(REPAIRED)
    return spec


NOT_STARTED = suite.AcceptanceResult(ran=True, exit_code=1, report=junit.Report(found=True, tests=[
    junit.TestResult(name="[AC-1] a", outcome="failed", message=FAILED_ON_SETUP),
    junit.TestResult(name="[AC-2] b", outcome="failed", message=FAILED_ON_SETUP)]))


def test_a_version_measured_while_the_product_did_not_start_is_not_kept_as_the_best(tmp_path):
    _reopened_while_the_product_does_not_start(tmp_path)

    assert suite.keep_the_best_of_the_repair(tmp_path, NOT_STARTED) is False


def test_with_no_best_kept_the_lock_comes_back(tmp_path):
    spec = _reopened_while_the_product_does_not_start(tmp_path)
    suite.keep_the_best_of_the_repair(tmp_path, NOT_STARTED)

    suite.put_back_the_best_of_the_repair(tmp_path)

    assert spec.read_text() == LOCKED


def test_a_repair_opened_before_the_one_repair_record_still_puts_back_its_best_version(tmp_path):
    """A workspace a repair was open in when the harness changed: its earlier stores are read as the record."""
    (tmp_path / ".project-directory").write_text("notes\n")
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text(LOCKED)
    suite.lock(tmp_path)
    suite.unlock(tmp_path)
    saved = tmp_path / ".harness" / "acceptance.json"
    saved.write_text(json.dumps({**json.loads(saved.read_text()), "repairing": ["[AC-1] a"],
                                 "repair_bodies": {"[AC-1] a": "test('[AC-1] a', ...)"},
                                 "before_repair": {"tests": 2, "passed": 0},
                                 "repair_best": {"tests": 2, "passed": 1, "changed": ["[AC-1] a"]}}))
    earlier_best = tmp_path / ".harness" / "acceptance-repair-best" / "notes" / "acceptance"
    earlier_best.mkdir(parents=True)
    (earlier_best / "notes.spec.js").write_text(REPAIRED)
    spec.write_text(LOCKED + "test('[AC-3] c', async () => {});\n")

    suite.put_back_the_best_of_the_repair(tmp_path)

    assert spec.read_text() == REPAIRED
