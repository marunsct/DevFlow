"""A defect's call ceiling is reached: an attempt that would pass it is not started, and the calls of one problem are
counted under every key it was raised with (deep review of silent mechanisms, 2026-11-25).

The ceiling (60 calls) was checked only before an attempt, and an attempt costs 16 to 20 calls: measured, one defect
had spent 20, 18 and 17 calls over three attempts across a re-plan, was given a fourth at 55 and ended at 75; no defect
in 30 runs was ever left open by the ceiling.
"""
from __future__ import annotations

import os
from unittest import mock

from app.graph import cause_journal, defect_budget
from app.sprint import Defect, RemediationCycle

ON = {"DEFECT_CALL_CAP": "on", "DEFECT_CALLS_AT_MOST": ""}
#: How the measured defect was raised, word for word.
TIMED_OUT = ("The unit tests fail. The runner's output ends: Command timed out after 300 seconds. A command that does "
             "not finish is usually one that was not meant to: a server")
CRITERION = "[AC-4] Filter the list by tag - the acceptance suite says this does not work yet"


def _fresh_cycle(description=TIMED_OUT, **fields):
    defect = Defect(description=description, severity="major", reproduction_steps="r", expected_behavior="e",
                    actual_behavior="a", owner="backend", **fields)
    return RemediationCycle(sprint_goal="g", defects=[defect])


def test_a_fourth_attempt_that_would_pass_the_ceiling_is_not_started():
    """The measured attempts: 20 and 18 before the re-plan, 17 after it, each kept in the run's ledger."""
    with mock.patch.dict(os.environ, ON), \
            mock.patch.object(defect_budget, "_attempts_in_the_run", lambda ids: ["20", "18", "17"]):
        why = defect_budget.spent_out(_fresh_cycle(), 0)

    assert "55 model calls" in why and "at most 60" in why


def test_a_third_attempt_that_stays_under_it_is_started():
    with mock.patch.dict(os.environ, ON), \
            mock.patch.object(defect_budget, "_attempts_in_the_run", lambda ids: ["20", "18"]):
        assert defect_budget.spent_out(_fresh_cycle(), 0) == ""


def _journalled(root, calls_by_key):
    """Earlier attempts at one criterion, each raised under the cause key its failing tests gave it then."""
    for key, calls in calls_by_key:
        earlier = _fresh_cycle(CRITERION, source="acceptance suite", cause_key=key).defects[0]
        cause_journal.record(root, earlier, {"stage": "defect_fix_1_0", "files": ["src/list.js"], "did": "d",
                                             "outcome": "left open: its tests still fail", "calls": calls})


def test_one_problem_raised_under_new_keys_is_counted_from_the_fix_journal(tmp_path):
    """A criterion's failing tests change between attempts, so its cause key and its ledger id change with them."""
    _journalled(tmp_path, [("failing_test:test:adds one", 25), ("failing_test:test:adds two", 20),
                           ("failing_test:test:adds three", 18)])
    now = _fresh_cycle(CRITERION, source="acceptance suite", cause_key="failing_test:test:adds four")

    with mock.patch.dict(os.environ, ON), mock.patch.object(defect_budget, "_attempts_in_the_run", lambda ids: []):
        assert defect_budget.spent(now, 0, tmp_path) == 63
        assert defect_budget.spent_out(now, 0, tmp_path)


def test_the_fix_stage_does_not_start_a_fixer_for_a_problem_spent_under_other_keys(tmp_path):
    import the_fix_stage

    _journalled(tmp_path, [("failing_test:test:adds one", 32), ("failing_test:test:adds two", 30)])
    now = the_fix_stage.a_defect(CRITERION, source="acceptance suite", cause_key="failing_test:test:adds three")

    with mock.patch.dict(os.environ, ON), mock.patch.object(defect_budget, "_attempts_in_the_run", lambda ids: []):
        update, seen = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, now))

    assert seen.requests == [] and seen.agent_models == []
    assert update["defect_cursor"] == 1


def test_an_attempt_s_calls_are_kept_in_the_journal(tmp_path):
    from app.graph import workflow

    cycle = _fresh_cycle(CRITERION, source="acceptance suite", cause_key="failing_test:test:a")
    workflow._with_the_attempt(cycle, 0, "defect_fix_1_0", None, "left open", 17, root=str(tmp_path))

    assert cause_journal.calls_on_the_problem(tmp_path, cycle.defects[0]) == [17]
