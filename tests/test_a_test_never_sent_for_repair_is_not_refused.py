"""A locked test nobody ever asked QA to fix is not refused for a budget other tests spent.

Measured on one run: both of its suite repairs went on tests a harness check
had wrongly named (since fixed). Two login tests then called `.json()` on the
plain object their own helper returned - `TypeError: res.json is not a
function`, which no product can pass - and the suite could not be reopened:
two fix stages in turn answered "a bug in the locked test", and the criteria
waited on tests nothing could fix. The budget is to stop QA going round on the
same tests; a test never sent for repair now earns one, up to a ceiling.
"""

from __future__ import annotations

from app.graph import acceptance_nodes
from app.graph.acceptance_nodes import (
    MAX_SUITE_REPAIRS,
    MAX_SUITE_REPAIRS_IN_ALL,
    beyond_repair,
    may_repair,
    reopen_the_suite_for,
)

BROKEN = [
    "`[AC-1][AC-8] logging in with wrong password returns 401` fails because of an error in the "
    "test's own code, not because the product is unbuilt: TypeError: res.json is not a function.",
]


def _state(**extra):
    return {"repository": None, **extra}


def test_within_the_budget_any_test_is_repaired():
    assert may_repair(_state(suite_repairs=0), BROKEN)
    assert may_repair(_state(suite_repairs=MAX_SUITE_REPAIRS - 1), BROKEN)


def test_a_test_never_sent_earns_a_repair_past_the_budget(monkeypatch):
    monkeypatch.setattr(acceptance_nodes, "_decide", lambda *a, **k: None)
    state = _state(suite_repairs=MAX_SUITE_REPAIRS, suite_repaired_tests=["[AC-7] lists tasks"])

    reopened = reopen_the_suite_for(state, BROKEN)

    assert reopened is not None and reopened["stage"] == "acceptance_author"
    assert reopened["suite_repairs"] == MAX_SUITE_REPAIRS + 1
    assert "[AC-1][AC-8] logging in with wrong password returns 401" in reopened["suite_repaired_tests"]
    assert beyond_repair(state, BROKEN) == []


def test_the_same_tests_are_not_sent_round_again():
    state = _state(
        suite_repairs=MAX_SUITE_REPAIRS,
        suite_repaired_tests=["[AC-1][AC-8] logging in with wrong password returns 401"],
    )

    assert not may_repair(state, BROKEN)
    assert reopen_the_suite_for(state, BROKEN) is None
    assert beyond_repair(state, BROKEN) == ["AC-1", "AC-8"]


def test_there_is_a_ceiling_in_all():
    state = _state(suite_repairs=MAX_SUITE_REPAIRS_IN_ALL, suite_repaired_tests=[])

    assert not may_repair(state, BROKEN)
    assert beyond_repair(state, BROKEN) == ["AC-1", "AC-8"]


def test_a_dispute_is_held_for_tests_never_sent(monkeypatch):
    from app.graph import workflow

    monkeypatch.setattr(workflow, "_the_locked_tests_still_failing",
                        lambda state: [("[AC-8] logging in with a non-existent email returns 401", "AC-8", "TypeError")])
    monkeypatch.setattr(workflow, "_this_attempt", lambda state: "1:1")

    assert workflow._a_dispute_may_be_held_now(_state(suite_repairs=MAX_SUITE_REPAIRS, suite_repaired_tests=["x"]))
    assert not workflow._a_dispute_may_be_held_now(_state(
        suite_repairs=MAX_SUITE_REPAIRS,
        suite_repaired_tests=["[AC-8] logging in with a non-existent email returns 401"],
    ))


def test_the_state_carries_what_was_sent():
    from app.graph.workflow import WorkflowGraphState

    assert "suite_repaired_tests" in WorkflowGraphState.__annotations__
