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

import the_fix_stage

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


def _the_fixer_s_model(monkeypatch, tmp_path, node: str, defect: Defect) -> str:
    build, judge = the_fix_stage.two_models(monkeypatch)
    state = the_fix_stage.a_state(tmp_path, defect, __fix_index=0)
    _, seen = the_fix_stage.run(tmp_path, state, node=node, model=build)
    [chosen] = seen.agent_models
    return chosen.name


def test_the_fix_stages_ask_the_question(monkeypatch, tmp_path) -> None:
    """Both fix dispatch sites - the single fixer and the batched one - send the fix after one revert to the
    judgement model, though its failed tries are below the generic rung; without a revert, the build model."""
    from app.models.roles import escalate_after

    assert 1 < escalate_after(), "one failed try is below the generic rung"
    for node in ("defect_remediation", "defect_fix_worker"):
        assert _the_fixer_s_model(monkeypatch, tmp_path, node, _defect(fix_attempts=1)) == "build", node
        reverted = _defect(actual_behavior=f"a\n{SINGLE}", fix_attempts=1)
        assert _the_fixer_s_model(monkeypatch, tmp_path, node, reverted) == "judge", node
