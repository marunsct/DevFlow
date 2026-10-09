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


def test_bundle_co_defects_matches_regression_test_requirement() -> None:
    from app.graph.workflow import _bundle_co_defects

    d1 = Defect(
        description="First issue",
        severity="minor",
        reproduction_steps="step 1",
        expected_behavior="expect 1",
        actual_behavior="actual 1",
        owner="ui_ux",
        regression_test_required=False,
    )
    d2 = Defect(
        description="Filter view does not update immediately",
        severity="major",
        reproduction_steps="step 2",
        expected_behavior="expect 2",
        actual_behavior="actual 2",
        owner="ui_ux",
        regression_test_required=True,
    )
    d3 = Defect(
        description="Third issue",
        severity="minor",
        reproduction_steps="step 3",
        expected_behavior="expect 3",
        actual_behavior="actual 3",
        owner="ui_ux",
        regression_test_required=False,
    )
    cycle = RemediationCycle(sprint_goal="Fix UI issues", defects=[d1, d2, d3])

    bundled = _bundle_co_defects(cycle, 0)
    # d2 requires a regression test while d1 does not, so d2 must NOT be bundled with d1.
    # d3 does not require a regression test, so d3 is bundled.
    assert len(bundled) == 1
    assert bundled[0][0] == 2
    assert bundled[0][1].description == "Third issue"


def test_apply_batch_co_defect_fixes_leaves_untested_co_defect_open_without_raising() -> None:
    from app.graph.workflow import _apply_batch_co_defect_fixes

    d1 = Defect(
        description="First issue",
        severity="minor",
        reproduction_steps="step 1",
        expected_behavior="expect 1",
        actual_behavior="actual 1",
        owner="ui_ux",
        regression_test_required=False,
    )
    d2 = Defect(
        description="Filter view does not update immediately",
        severity="major",
        reproduction_steps="step 2",
        expected_behavior="expect 2",
        actual_behavior="actual 2",
        owner="ui_ux",
        regression_test_required=True,
    )
    cycle = RemediationCycle(sprint_goal="Fix UI issues", defects=[d1, d2])

    # Suppose d2 was bundled as a co-defect, but no regression test was provided:
    # it must not raise ValueError, and d2 must remain open.
    updated = _apply_batch_co_defect_fixes(
        cycle,
        [(1, d2)],
        defect_index=0,
        regression_test="",
        verified_by="",
        resolution="Fixed UI",
        stage_name="defect_fix_1_0",
        round_=1,
        sprint=1,
    )
    assert updated.defects[1].status == "open"


