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
