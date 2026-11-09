"""A failing unit run beside a locked suite that passes in full is told the unit test may be the one that is wrong.

Measured on two runs: the unit tests that shipped failing asserted a key order, a count other tests' data changed, and
an empty 404 body the interface does not give; the fixers changed the product for them and were reverted.
"""
from __future__ import annotations

import inspect
import re

from app.graph import workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_beside_a_green_suite_the_defect_says_the_unit_test_may_be_wrong():
    defect = workflow._the_unit_tests_fail(None, "1 failing", beside_a_green_suite=True)
    assert workflow.BESIDE_A_GREEN_SUITE in defect.actual_behavior
    assert defect.description.startswith(workflow.UNIT_TESTS_FAIL)
    assert not BANNED.search(workflow.BESIDE_A_GREEN_SUITE)


def test_otherwise_it_does_not():
    assert workflow.BESIDE_A_GREEN_SUITE not in workflow._the_unit_tests_fail(None, "1 failing").actual_behavior


def test_the_harness_round_says_it_when_nothing_due_fails():
    source = inspect.getsource(workflow)
    assert 'beside_a_green_suite=not failing_due and int(saved_run.get("failed") or 0) == 0' in source
