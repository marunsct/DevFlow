"""A defect's model calls are counted across its fix attempts, and one that has spent the ceiling is not fixed again (plan AY step 4).

Behind `DEFECT_CALL_CAP`, off until measured: each attempt re-armed its own
stage budget, so a defect fixed in three rounds cost three budgets.
"""
from __future__ import annotations

import inspect
import os
import re
from types import SimpleNamespace
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


def test_the_start_is_carried_across_a_pause(tmp_path, monkeypatch):
    """Taken again on resume, the calls before the pause were not counted."""
    from workflow_node_stubs import run_a_fixer

    monkeypatch.setattr(defect_budget, "now", lambda: "NOW")

    resumed = run_a_fixer(monkeypatch, tmp_path, fix_started="BEFORE THE PAUSE", pending_inner_thread_id="inner")
    first = run_a_fixer(monkeypatch, tmp_path, fix_started="A STALE START")

    assert resumed.update["fix_started"] == "BEFORE THE PAUSE"
    assert first.update["fix_started"] == "NOW"


def test_a_batch_s_start_is_cleared_when_the_batch_is_settled(tmp_path, monkeypatch):
    from app.agents.specialists import SpecialistOutput
    from workflow_node_stubs import CONFIG, compiled, one_defect

    cycle = one_defect()
    monkeypatch.setattr("app.graph.engineering.after_a_fix", lambda *a, **k: [])
    monkeypatch.setattr(workflow, "_settle_the_fix", lambda state, cycle, *a, **k: (
        {"remediation": cycle, "specialist_outputs": {}}, False))
    graph = compiled(monkeypatch, tmp_path)
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "remediation": cycle, "fix_batch": [0], "fix_batch_started": "THE BATCH'S START", "test_round": 1,
             "specialist_outputs": {"defect_fix_1_0": SpecialistOutput(changed_files=["app/store.js"])}}

    update = graph.nodes["defect_fix_gather"].bound.invoke(state, CONFIG)

    assert update["fix_batch"] == [] and update["fix_batch_started"] == ""


# The attempt records live on the remediation cycle, and a re-planned sprint starts a new one: measured over 30 runs,
# six defects went past the cap this way (523 calls, 288 model minutes; 132 calls on one) and five were never fixed.
def test_a_defect_re_planned_into_a_new_cycle_keeps_the_calls_it_spent_before():
    from app.observability.defect_ledger import defect_id

    earlier = _cycle()
    the_same = earlier.defects[0]
    ledger = [
        {"kind": "defect", "event": defect_budget.ATTEMPT_EVENT, "defect_id": defect_id(the_same), "detail": "34"},
        {"kind": "defect", "event": defect_budget.ATTEMPT_EVENT, "defect_id": defect_id(the_same), "detail": "29"},
        {"kind": "defect", "event": defect_budget.ATTEMPT_EVENT, "defect_id": "someother1", "detail": "50"},
        {"kind": "defect", "event": "left open", "defect_id": defect_id(the_same), "detail": "its own tests still fail"},
    ]
    fresh_cycle = _cycle()  # the re-plan's new cycle: no attempts on it yet
    with mock.patch.dict(os.environ, ON), \
         mock.patch("app.observability.transcript._run_id_from_config", lambda: "run"), \
         mock.patch("app.observability.transcript.read_transcript", lambda run_id, kinds=None: ledger):
        assert defect_budget.spent(fresh_cycle, 0) == 63
        assert "63 model calls" in defect_budget.spent_out(fresh_cycle, 0)
        assert defect_budget.spent(_cycle(70), 0) == 70, "the cycle's own count when it is more"


def test_each_counted_attempt_is_noted_in_the_ledger():
    noted = []
    with mock.patch("app.observability.defect_ledger.note",
                    lambda event, stage, **kw: noted.append((event, stage, kw.get("detail")))):
        workflow._with_the_attempt(_cycle(), 0, "defect_fix_2_0", None, "left open", 17)
        workflow._with_the_attempt(_cycle(), 0, "defect_fix_2_0", None, "left open", None)
    assert noted == [(defect_budget.ATTEMPT_EVENT, "defect_fix_2_0", "17")]
