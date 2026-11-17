"""A passing locked test that two reverted fixes broke is disputed even when the failing tests' repairs are spent.

Measured on one run: every fix of AC-5 (DELETE answers 204) was reverted for breaking AC-7's "DELETE returns JSON",
five times over two attempts. The dispute was not held: its gate asked whether the *failing* tests could be repaired
again, and they had been, while the contested test - passing, never sent - could still be.
"""
from __future__ import annotations

from app.graph import acceptance_nodes, workflow

FAILING = [("[AC-5] DELETE /notes/:id removes the note", "a.spec.js", "Expected: 204 Received: 200")]
CONTESTED = "acceptance: ac_content_type.spec.js › [AC-7] DELETE /notes/1 returns Content-Type application/json"


def _state():
    return {"suite_repairs": acceptance_nodes.MAX_SUITE_REPAIRS,
            "suite_repaired_tests": ["[AC-5] DELETE /notes/:id removes the note"],
            "disputed_sprints": []}


def test_a_contested_test_never_sent_lets_the_dispute_be_held(monkeypatch):
    monkeypatch.setattr(workflow, "_the_locked_tests_still_failing", lambda state: FAILING)
    monkeypatch.setattr(workflow, "_this_attempt", lambda state: "1:2")

    assert workflow._a_dispute_may_be_held_now(_state()) is False, "the failing tests alone are spent"
    assert workflow._a_dispute_may_be_held_now(_state(), also=[CONTESTED]) is True


def test_once_an_attempt_still_holds(monkeypatch):
    monkeypatch.setattr(workflow, "_the_locked_tests_still_failing", lambda state: FAILING)
    monkeypatch.setattr(workflow, "_this_attempt", lambda state: "1:2")
    state = {**_state(), "disputed_sprints": ["1:2"]}

    assert workflow._a_dispute_may_be_held_now(state, also=[CONTESTED]) is False


def test_the_revert_branch_asks_with_the_contested_test(monkeypatch, tmp_path):
    """A second fix reverted for breaking the same passing locked test holds the dispute, though the failing tests'
    repairs are spent: the contested test is what the dispute is asked about."""
    import the_fix_stage

    monkeypatch.setattr(workflow, "_the_locked_tests_still_failing", lambda state: FAILING)
    monkeypatch.setattr(workflow, "_this_attempt", lambda state: "1:2")
    first = the_fix_stage.a_state(tmp_path, the_fix_stage.a_defect("[AC-5] DELETE answers 204"))["remediation"]
    reverted_once = workflow._noted_as_reverted(first, [0], [CONTESTED])
    state = {**the_fix_stage.a_state(tmp_path, *reverted_once.defects), **_state()}

    update, _ = the_fix_stage.run(tmp_path, state, broke=[CONTESTED])

    assert update.get("stage") == "acceptance_dispute" and update["dispute_returns_to"] == "test_and_triage"
    assert CONTESTED in update["dispute_reason"]
