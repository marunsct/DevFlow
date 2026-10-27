"""A failing-unit-tests fix reverted for breaking the locked acceptance suite is told the unit tests are out of date.

Measured on one run: the unit tests called the product's factory as it was before a fix made it asynchronous; two
fixes in turn changed the product to suit them, broke three and then seven passing acceptance tests, and were
reverted, and the sprint was planned again.
"""
from __future__ import annotations

import re

from app.agents.specialists import ReportedDefect
from app.graph import workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class _Cycle:
    def __init__(self, defects):
        self.defects = defects

    def model_copy(self, update):
        return _Cycle(update["defects"])


def _defect(description):
    return ReportedDefect(description=description, severity="major", reproduction_steps="r",
                          expected_behavior="e", actual_behavior="a", affected_files=[], owner="backend")


def test_a_unit_test_defect_that_broke_acceptance_tests_is_told_to_change_the_unit_tests():
    cycle = _Cycle([_defect(workflow.UNIT_TESTS_FAIL + " It says: undefined !== 201")])
    noted = workflow._noted_as_reverted(cycle, [0], ["acceptance: notes.spec.js › [AC-1] creates a note"])
    said = noted.defects[0].actual_behavior
    assert "the unit tests are out of date" in said and "leave the product as it is" in said
    assert not BANNED.search(workflow.UNIT_TESTS_AGAINST_THE_SUITE)


def test_a_product_defect_or_a_unit_only_break_is_not_told_so():
    product = _Cycle([_defect("[AC-1] Create a note - the acceptance suite says this does not work yet.")])
    said = workflow._noted_as_reverted(product, [0], ["acceptance: notes.spec.js › [AC-2] lists"]).defects[0].actual_behavior
    assert "unit tests are out of date" not in said
    unit = _Cycle([_defect(workflow.UNIT_TESTS_FAIL)])
    said = workflow._noted_as_reverted(unit, [0], ["unit: app.test.ts › creates"]).defects[0].actual_behavior
    assert "unit tests are out of date" not in said
