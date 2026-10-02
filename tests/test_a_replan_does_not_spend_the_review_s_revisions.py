"""A sprint planned again for its tests keeps the milestone review's revisions.

Both were counted on `milestone_revision_count`. Measured on one run: one
re-plan after three test rounds, then two milestone reviews - the first blocked
on a `require` in an ES module, which was fixed; the second raised four
findings, none of them the first's - and the run ended "after 3 revisions", ten
minutes in, on the first review whose findings nobody had been given a chance
to fix.
"""

from __future__ import annotations

import inspect

from app.graph import workflow


def _replan_source() -> str:
    source = inspect.getsource(workflow)
    start = source.index("def _replan_or_escalate(")
    return source[start:source.index("def defect_remediation_node(", start)]


def test_a_replan_is_counted_on_its_own_counter() -> None:
    body = _replan_source()

    assert 'state.get("sprint_replan_count", 0) + 1' in body
    assert "sprint_replan_count=revision_count" in body
    # The review's counter is not written on this path at all.
    assert "milestone_revision_count=" not in body


def test_the_replan_is_still_bounded() -> None:
    assert "if revision_count > MAX_MILESTONE_REVISIONS:" in _replan_source()


def test_both_counters_start_again_with_the_next_sprint() -> None:
    source = inspect.getsource(workflow)
    advance = source[source.index('"revision_comments": [],'):][:200]

    assert '"milestone_revision_count": 0' in advance
    assert '"sprint_replan_count": 0' in advance
    assert workflow._REWIND_COUNTER_RESETS["milestone_review"] == {
        "milestone_revision_count": 0, "sprint_replan_count": 0,
    }


def test_the_state_declares_it() -> None:
    assert "sprint_replan_count" in workflow.WorkflowGraphState.__annotations__
