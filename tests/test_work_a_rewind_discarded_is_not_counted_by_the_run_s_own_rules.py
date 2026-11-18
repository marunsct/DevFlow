"""Work a rewind discarded is not counted by the rules that read the run's transcript.

Deep review 2026-11-18, item D2b: a rewind puts the checkpoint and the workspace (`.harness/` side files included)
back to the start of a stage, but the transcript is the run's own and keeps what the abandoned branch did. The KPIs
already left that work out (`run_kpis.live_branch`); the rules that read the transcript for attempt state did not:
a defect's model calls on the discarded branch still counted against its budget after the rewind, and a review that
ran only on the discarded branch still counted as having read the code.
"""

from __future__ import annotations

import json
import os
from unittest import mock

from langchain_core.runnables import RunnableLambda

from app.graph import defect_budget
from app.observability.defect_ledger import defect_id
from app.observability.transcript import read_live
from app.sprint import Defect, RemediationCycle
from app.tracing import APP_RUN_ID_KEY


def _at(minute: int) -> str:
    return f"2026-11-18T10:{minute:02d}:00+00:00"


def _a_transcript(tmp_path, monkeypatch, run_id: str, records: list[dict]) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "transcripts").mkdir(exist_ok=True)
    lines = [json.dumps({"run_id": run_id, **record}) for record in records]
    (tmp_path / "transcripts" / f"{run_id}.jsonl").write_text("\n".join(lines) + "\n")


def _defect() -> Defect:
    return Defect(description="The items route answers 500 on create", severity="major", reproduction_steps="r",
                  expected_behavior="e", actual_behavior="a", owner="backend", status="open", attempts=[])


def _rewound_at(minute: int, back_to: int) -> dict:
    return {"kind": "rewound", "stage": "technical_lead", "at": _at(minute), "point_at": _at(back_to)}


def test_a_defect_s_calls_on_a_discarded_branch_do_not_count_against_its_budget(tmp_path, monkeypatch):
    defect = _defect()
    _a_transcript(tmp_path, monkeypatch, "run-budget", [
        {"kind": "defect", "stage": "defect_fix_1_0", "at": _at(5), "event": defect_budget.ATTEMPT_EVENT,
         "defect_id": defect_id(defect), "detail": "12"},
        {"kind": "defect", "stage": "defect_fix_1_0", "at": _at(20), "event": defect_budget.ATTEMPT_EVENT,
         "defect_id": defect_id(defect), "detail": "50"},
        _rewound_at(30, back_to=10),
    ])
    cycle = RemediationCycle(sprint_goal="g", defects=[defect])

    with mock.patch.dict(os.environ, {"DEFECT_CALL_CAP": "on"}):
        used = RunnableLambda(lambda _: defect_budget.spent(cycle, 0)).invoke(
            None, config={"configurable": {APP_RUN_ID_KEY: "run-budget"}})

    assert used == 12


def test_the_live_records_leave_out_what_a_rewind_discarded_and_keep_the_rest(tmp_path, monkeypatch):
    _a_transcript(tmp_path, monkeypatch, "run-live", [
        {"kind": "model_request", "stage": "milestone_review", "at": _at(5)},
        {"kind": "model_request", "stage": "security_review", "at": _at(15)},
        _rewound_at(30, back_to=10),
        {"kind": "model_request", "stage": "technical_lead", "at": _at(31)},
    ])

    live = read_live("run-live", {"model_request"})

    assert [r["stage"] for r in live] == ["milestone_review", "technical_lead"]
