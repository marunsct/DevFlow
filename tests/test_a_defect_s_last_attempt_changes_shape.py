"""A defect's last permitted attempt asks for a different shape of work.

L.4/L.5 change who fixes and when the loop stops; this changes what is asked
(Initiative L.6). A defect that has failed `escalate_after()` fixes is on its
last rung - after this one it is left open and the round counts it - and every
attempt so far had the same shape: patch the lines the failure names. The
opinion review's point was "terminate with a different strategy": the last
attempt's work order demands a whole-file rewrite of the implicated files,
with a named blocker as the way out when the specification itself cannot
produce a passing file, instead of a third variation of the instruction that
failed twice.
"""

from __future__ import annotations

import inspect
import re

from app.graph import workflow
from app.sprint import Defect, RemediationCycle


def _defect(**extra) -> Defect:
    fields: dict = {
        "description": "AC-4 Delete: removes every record", "severity": "blocking",
        "reproduction_steps": "r", "expected_behavior": "e", "actual_behavior": "a",
        "owner": "backend", "affected_files": ["src/app.js"],
    }
    fields.update(extra)
    return Defect(**fields)


def _cycle(*defects: Defect) -> RemediationCycle:
    return RemediationCycle(sprint_goal="Sprint 2", defects=list(defects))


def test_an_attempt_below_the_escalation_rung_gets_the_usual_order() -> None:
    assert workflow._the_last_attempt_section(_cycle(_defect(fix_attempts=1)), 0) == ""


def test_a_defect_that_never_failed_gets_nothing_extra() -> None:
    assert workflow._the_last_attempt_section(_cycle(_defect()), 0) == ""


def test_the_last_permitted_attempt_changes_the_shape_of_the_order() -> None:
    section = workflow._the_last_attempt_section(_cycle(_defect(fix_attempts=2)), 0)

    assert "after 2 that failed" in section
    assert "Rewrite `src/app.js` whole" in section
    assert "blocker" in section
    # The earlier attempts' evidence is pointed at, not repeated blind.
    assert "notes above" in section


def test_a_defect_with_no_named_files_still_gets_a_rewrite_order() -> None:
    section = workflow._the_last_attempt_section(
        _cycle(_defect(fix_attempts=3, affected_files=[])), 0
    )

    assert "each file the failure names" in section


def test_the_shape_change_reaches_the_fix_request() -> None:
    source = inspect.getsource(workflow)
    assert "request[\"messages\"][-1][\"content\"] += _the_last_attempt_section(cycle, defect_index)" in source


def test_the_last_attempt_order_names_no_product_word() -> None:
    banned = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")
    section = workflow._the_last_attempt_section(_cycle(_defect(fix_attempts=2)), 0)

    for word in banned:
        assert not re.search(rf"\b{re.escape(word)}\b", section, re.IGNORECASE), word
