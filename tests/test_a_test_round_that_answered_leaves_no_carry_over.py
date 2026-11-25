"""A test round that answers spends its restart's note: its next visit opens without it (LF.1467).

Measured on one medium run: a test round's first attempt ended without a structured response and the second opened
on a carry-over note; the second answered (the answer below), the sprint was re-planned, two builders changed the
code, and the round's next visit opened on the same note - "your previous attempt ended without a structured
response" and a work note written before the code changed. The round built its update without the spent note, so
the state kept it. The note and the answer are that run's, captured from the transcript.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.agents.specialists import SpecialistOutput

CAPTURED = json.loads((Path(__file__).parent / "captured" / "test_round_answer_after_a_restart.json").read_text("utf-8"))


class _Agent:
    """The round's agent: answers at once with the captured answer."""

    def __init__(self, answer):
        self.answer = answer

    def get_state(self, config):
        return SimpleNamespace(values={}, next=())

    def invoke(self, request, config=None):
        return {"messages": [], "structured_response": self.answer}


def test_the_round_s_update_drops_the_note_it_was_restarted_with(monkeypatch, tmp_path):
    from workflow_node_stubs import run_a_test_round

    from app.graph import workflow

    answer = SpecialistOutput(**CAPTURED["answer"])
    note = CAPTURED["carry_over_note"]
    assert note.startswith("[Carrying over from your previous attempt at this stage")

    seen = run_a_test_round(
        monkeypatch, tmp_path, failing_due=["AC-1"],
        overrides={"app.graph.workflow._run_gated_agent": workflow._run_gated_agent,
                   "app.graph.workflow.create_specialist_agent": lambda *a, **k: _Agent(answer)},
        stage_carry_over={"test_round_1": note, "specialist_backend_0": "its own note"},
        structured_retries={"test_round_1": 1},
    )

    assert "test_round_1" not in seen.update["stage_carry_over"]
    assert seen.update["stage_carry_over"]["specialist_backend_0"] == "its own note"
    assert "test_round_1" not in seen.update["structured_retries"]
