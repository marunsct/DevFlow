"""A regressed unit test may be out of date rather than the product broken.

Measured on one run: sprint 1 wrote unit tests pinning a placeholder filter,
and sprint 4 was the sprint that built filtering. CI reported both tests as
regressions, expected to "pass, as they did before". The one fix tried put the
placeholder back, broke four acceptance criteria and was reverted, and the
sprint failed on exhausted attempts with 72 of 73 tests passing.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from app.graph.engineering import _OR_THE_TEST_IS_OUT_OF_DATE, regression_defects


def _state() -> dict:
    task = SimpleNamespace(specialist_role="backend", title="Build it", task_description="")
    return {"milestone_plan": SimpleNamespace(delegated_tasks=[task])}


def test_a_unit_test_s_regression_names_the_other_possibility() -> None:
    [defect] = regression_defects(_state(), ["unit: filter › returns everything (placeholder)"])

    assert "out of date" in defect.expected_behavior
    assert "keep the test's name" in defect.expected_behavior


def test_the_locked_suite_s_regression_does_not() -> None:
    """No fix may change the acceptance suite, so it is never out of date to them."""
    [defect] = regression_defects(_state(), ["acceptance: flow.spec.js › [AC-2] marks it done"])

    assert defect.expected_behavior == "It passes, as it did before this sprint's work orders."


def test_it_names_no_product_and_no_control() -> None:
    text = _OR_THE_TEST_IS_OUT_OF_DATE.lower()
    for word in ("task", "to-do", "todo", "button", "click", "checkbox", "filter"):
        assert not re.search(rf"\b{word}\b", text), word


class TestATestThatIsGone:
    """A regressed test that did not run at all is gone, not failing.

    Measured on one run: a batch replaced four unit tests of a placeholder with
    tests of what replaced it. CI reported them passing before and failing now;
    four fix stages looked for a failing test, found none, and one answered
    "unable to identify failure cause"."""

    @staticmethod
    def _after(**unit: str):
        from app import ci

        return ci.Snapshot(label="after the work orders", unit=dict(unit), unit_ran=True,
                           acceptance={"flow.spec.js › [AC-1] adds": "passed"}, acceptance_ran=True)

    def test_it_is_described_as_gone(self) -> None:
        after = self._after(**{"logic.test.js › filters by mode": "passed"})

        [defect] = regression_defects(_state(), ["unit: logic.test.js › returns all (placeholder)"], after)

        assert "is gone now" in defect.description
        assert "removed or renamed" in defect.actual_behavior
        assert "name that test in your answer and change nothing" in defect.expected_behavior

    def test_one_that_ran_and_failed_is_still_failing(self) -> None:
        after = self._after(**{"logic.test.js › returns all (placeholder)": "failed"})

        [defect] = regression_defects(_state(), ["unit: logic.test.js › returns all (placeholder)"], after)

        assert "fails now" in defect.description
        assert "out of date" in defect.expected_behavior

    def test_a_suite_that_did_not_run_is_not_called_gone(self) -> None:
        """A broken build runs nothing; every test in it is failing, not removed."""
        from app import ci

        after = ci.Snapshot(label="x", unit={}, unit_ran=False)

        [defect] = regression_defects(_state(), ["unit: logic.test.js › adds"], after)

        assert "fails now" in defect.description

    def test_the_note_names_no_product_and_no_control(self) -> None:
        from app.graph.engineering import _GONE_ON_PURPOSE

        text = _GONE_ON_PURPOSE.lower()
        for word in ("task", "to-do", "todo", "button", "click", "checkbox", "filter"):
            assert not re.search(rf"\b{word}\b", text), word
