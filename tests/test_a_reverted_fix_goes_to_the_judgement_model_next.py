"""A reverted fix goes to the judgement model next, once per defect.

Both reverted fixes in the live run came from the local build model, and
the bench pattern says why it matters: the local model drafts fine but its
fixes and reviews are the weak link. Today the judgement model takes over
only at the generic rung - `escalate_after()` failed tries - so the attempt
right after a revert, the one with the strongest proven signal that the
build model's shape of fix does not work, runs on the build model again.
The revert IS the proven failure signal: the next attempt goes to the
judgement model, capped at one such escalation per defect because a second
revert reaches the generic rung on its own (Initiative L.4).
"""

from __future__ import annotations

import inspect
import re

from app.graph import workflow
from app.sprint import Defect, RemediationCycle

SINGLE = "A fix was tried and reverted, because it broke what passed before it: AC-2 add."
BATCH = (
    "A batch of fixes including this one was reverted, because together they broke what "
    "passed before them: AC-2 add. It is fixed on its own next."
)


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


def test_a_defect_with_no_revert_does_not_escalate_early() -> None:
    assert workflow._a_revert_escalates_this_fix(_cycle(_defect()), 0) is False


def test_one_revert_escalates_the_next_attempt() -> None:
    cycle = _cycle(_defect(actual_behavior=f"a\n{SINGLE}", fix_attempts=1))

    assert workflow._a_revert_escalates_this_fix(cycle, 0) is True


def test_a_batch_revert_counts_as_one() -> None:
    cycle = _cycle(_defect(actual_behavior=f"a\n{BATCH}", fix_attempts=1))

    assert workflow._a_revert_escalates_this_fix(cycle, 0) is True


def test_a_second_revert_is_the_generic_rung_s_not_l4_s() -> None:
    """The cap, which protects cost: two reverts mean `failed_fix_tries` has
    reached the rung and the ladder escalates on its own - L.4 adds no second
    escalation of its own on top."""
    cycle = _cycle(_defect(actual_behavior=f"a\n{SINGLE}\n{SINGLE}", fix_attempts=2))

    assert workflow._a_revert_escalates_this_fix(cycle, 0) is False


def test_the_index_is_respected() -> None:
    cycle = _cycle(_defect(), _defect(actual_behavior=f"a\n{SINGLE}", fix_attempts=1))

    assert workflow._a_revert_escalates_this_fix(cycle, 0) is False
    assert workflow._a_revert_escalates_this_fix(cycle, 1) is True


def test_the_fix_stages_ask_the_question() -> None:
    source = inspect.getsource(workflow.build_workflow_graph)

    assert "after_a_revert=" in source
    model_choice = inspect.getsource(workflow)  # the helper's own definition
    assert "def _a_revert_escalates_this_fix" in model_choice
    # Both fix dispatch sites - the single fixer and the batched one.
    assert source.count("_a_revert_escalates_this_fix(") >= 2


def test_the_build_model_takes_the_revert_signal() -> None:
    source = inspect.getsource(workflow.build_workflow_graph)

    assert "after_a_revert: bool = False" in source
    assert re.search(r"if after_a_revert\b", source)


def test_the_escalation_words_are_plain_language() -> None:
    """The log line and helper text carry no interface words a product model
    is never asked about here - and no banned whole words either."""
    helper = inspect.getsource(workflow._a_revert_escalates_this_fix)
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{word}\b", helper, re.IGNORECASE), word
