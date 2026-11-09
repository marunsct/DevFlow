"""A defect's model calls are counted across its fix attempts, and one that has spent the ceiling is not fixed again (plan AY step 4).

Behind `DEFECT_CALL_CAP`, off until measured: each attempt re-armed its own
stage budget, so a defect fixed in three rounds cost three budgets.
"""
from __future__ import annotations

import inspect
import os
import re
from unittest import mock

from app.graph import defect_budget, workflow
from app.sprint import Defect, RemediationCycle

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ON = {"DEFECT_CALL_CAP": "on", "DEFECT_CALLS_AT_MOST": ""}


def _cycle(*calls):
    attempts = [{"stage": f"defect_fix_{n}_0", "did": "changed the token check", "outcome": "left open", "calls": c}
                for n, c in enumerate(calls, 1)]
    defect = Defect(description="[AC-2] Sign in fails", severity="major", reproduction_steps="r",
                    expected_behavior="e", actual_behavior="a", owner="backend", attempts=attempts)
    return RemediationCycle(sprint_goal="g", defects=[defect])


def test_under_the_ceiling_the_defect_is_fixed_again_and_at_it_it_is_left_open_with_its_diagnosis():
    with mock.patch.dict(os.environ, ON):
        assert defect_budget.spent_out(_cycle(25, 30), 0) == ""
        why = defect_budget.spent_out(_cycle(25, 30, 12), 0)
    assert "67 model calls" in why and "changed the token check" in why
    assert not BANNED.search(why)
    with mock.patch.dict(os.environ, {"DEFECT_CALL_CAP": "off"}):
        assert defect_budget.spent_out(_cycle(25, 30, 12), 0) == ""
    with mock.patch.dict(os.environ, {**ON, "DEFECT_CALLS_AT_MOST": "20"}):
        assert defect_budget.spent_out(_cycle(25), 0)


def test_an_attempt_s_calls_are_counted_from_the_transcript_since_it_started():
    records = [
        {"kind": "model_request", "stage": "defect_fix_1_0", "at": "2026-10-22T00:00:00+00:00"},
        {"kind": "model_request", "stage": "defect_fix_1_0", "at": "2026-10-22T01:00:01+00:00"},
        {"kind": "model_request", "stage": "defect_fix_1_0", "at": "2026-10-22T01:00:05+00:00"},
        {"kind": "model_request", "stage": "defect_fix_1_1", "at": "2026-10-22T01:00:06+00:00"},
        # A candidate rewrite for it, recorded under the family's name.
        {"kind": "model_request", "stage": "defect_fix", "at": "2026-10-22T01:00:07+00:00"},
    ]
    with mock.patch.dict(os.environ, ON), \
         mock.patch("app.observability.transcript.read_transcript", lambda run_id, kinds=None: records):
        assert defect_budget.calls_in("run", "defect_fix_1_0", "2026-10-22T01:00:00+00:00") == 3
        assert defect_budget.calls_in("run", "defect_fix_1_0", "") is None, "no start counts nothing"
    with mock.patch.dict(os.environ, {"DEFECT_CALL_CAP": "off"}):
        assert defect_budget.calls_in("run", "defect_fix_1_0", "2026-10-22T01:00:00+00:00") is None


def test_the_attempt_record_keeps_the_calls_and_the_fix_stage_checks_the_ceiling_first():
    cycle = workflow._with_the_attempt(_cycle(), 0, "defect_fix_1_0", None, "left open", 17)
    assert cycle.defects[0].attempts[-1]["calls"] == 17
    source = inspect.getsource(workflow)
    assert source.index("defect_budget.spent_out(cycle, defect_index)") < source.index("fix_model = _the_build_model(\n            state,\n            stage_name,")


def test_the_start_is_carried_across_a_pause_and_a_batch_s_start_is_cleared():
    source = inspect.getsource(workflow)
    fix_one = source[source.index("    def _fix_one("):source.index("    def _the_next_fix_batch(")]
    assert 'state.get("fix_started")' in fix_one and 'update["fix_started"] = started' in fix_one
    gather = source[source.index("    def defect_fix_gather_node("):source.index("    def _the_security_review(")]
    assert 'fix_batch_started=""' in gather
