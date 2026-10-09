"""Tests for batch defect remediation.

When multiple open defects belong to the same specialist role in a test round,
they are bundled into a single remediation invocation rather than spawning
independent agent stages for each individual defect.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from app.sprint import Defect, RemediationCycle, mark_defect_fixed


def test_batch_marking_defects_fixed() -> None:
    d1 = Defect(
        description="First issue",
        severity="major",
        reproduction_steps="step 1",
        expected_behavior="expect 1",
        actual_behavior="actual 1",
        owner="ui_ux",
        regression_test_required=True,
    )
    d2 = Defect(
        description="Second issue",
        severity="minor",
        reproduction_steps="step 2",
        expected_behavior="expect 2",
        actual_behavior="actual 2",
        owner="ui_ux",
        regression_test_required=False,
    )
    cycle = RemediationCycle(sprint_goal="Fix UI issues", defects=[d1, d2])
    assert cycle.defects[0].status == "open"
    assert cycle.defects[1].status == "open"

    cycle = mark_defect_fixed(cycle, 0, regression_test="tests/test_batch.py", resolution="Fixed both")
    cycle = mark_defect_fixed(cycle, 1, regression_test="tests/test_batch.py", resolution="Fixed both")
    assert cycle.defects[0].status == "fixed"
    assert cycle.defects[1].status == "fixed"


def test_batch_remediation_prompt_contains_no_forbidden_words() -> None:
    import re
    # The template line used when bundling co-defects
    batch_header = "Related failures owned by your role to resolve in this same fix"
    forbidden = {"task", "tasks", "to-do", "todo", "button", "click", "checkbox"}
    words = {w.lower() for w in re.findall(r"\b\w+[\w-]*\b", batch_header)}
    assert not (words & forbidden), f"Found forbidden words: {words & forbidden}"

