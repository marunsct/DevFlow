"""An escalation about the design leaves the build on the build model; one about stuck work still moves it up.

Measured on two hosted runs: the architecture review still asked for changes, the run built from the latest
specification anyway (an escalation of the design), and from then on every specialist, drafting and fix stage of every
sprint ran on the judgement model - 1.47M input tokens in one specialist stage - because the rung that moves a retried
sprint up read the same escalation count. A design escalation says nothing about whether the build model can build.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import escalation
from app.graph.context import GraphContext

BUILD, JUDGEMENT = object(), object()


def _context() -> GraphContext:
    return GraphContext(model=BUILD, judgement_model=JUDGEMENT, planning_model=BUILD, building_model=BUILD,
                        checkpointer=None, repo_root=None)


def test_a_design_escalation_leaves_the_build_on_the_build_model():
    state = {"escalation_count": 1, "design_escalation_count": 1}

    assert _context().the_model_for_this_attempt(state) is BUILD


def test_an_escalation_of_stuck_work_still_moves_the_build_up():
    assert _context().the_model_for_this_attempt({"escalation_count": 2, "design_escalation_count": 1}) is JUDGEMENT
    assert _context().the_model_for_this_attempt({"escalation_count": 1}) is JUDGEMENT


def test_the_design_escalation_is_counted_as_one(monkeypatch):
    seen = {}

    def _built(state, update, error, **kwargs):
        seen.update(update)
        return update

    monkeypatch.setattr(escalation, "_kind", lambda state: escalation.DESIGN)
    monkeypatch.setattr(escalation, "asks_a_person", lambda state: False)
    monkeypatch.setattr(escalation, "_build_from_the_latest_specification", _built)
    monkeypatch.setattr(escalation, "_after_the_specification", lambda state: "next")

    escalation.escalation({"escalation": {"error": "still asks for changes"}, "escalation_count": 0,
                           "repository": SimpleNamespace(root_path="/nowhere")},
                          {}, SimpleNamespace(judgement_model=None))

    assert seen == {"escalation_count": 1, "design_escalation_count": 1}


def test_the_count_is_kept_in_the_run_s_state():
    from app.graph.workflow import WorkflowGraphState

    assert "design_escalation_count" in WorkflowGraphState.__annotations__
