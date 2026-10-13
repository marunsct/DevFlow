"""In parallel mode the sprint's security review and its advice reviews run side by side.

Each reads the finished sprint and none reads another's verdict; the milestone
review, which weighs them all, waits for `review_gather`. Against a model API
that serves requests at once, that is their combined wait saved every sprint.
"""

from __future__ import annotations

import dataclasses
import logging

import pytest

from app.agents.advice_review import AdviceReview
from app.graph import workflow as workflow_module
from app.graph.workflow import start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    _approved_review,
    _document,
    _graph,
    _repository,
    _script_through_sprint,
    _spec,
    agents,
    responds_with,
)


@pytest.fixture
def parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    real = config.load_settings()
    monkeypatch.setattr(
        config, "load_settings", lambda *args, **kwargs: dataclasses.replace(real, execution_mode="parallel"),
    )


def _a_sprint_with_advice_reviews(agents, monkeypatch) -> None:
    from test_the_specialists_advise_before_the_specification import TestThroughTheGraph as Consulting

    from app.agents.specialist_advice import SpecialistAdvice

    Consulting._consulting(monkeypatch, agents, ["ui_ux", "database"], reviewing=True)
    Consulting._script_the_stack(agents)
    monkeypatch.setattr(
        workflow_module, "create_advice_reviewer_agent",
        lambda role, *args, **kwargs: agents.agent(f"advice_reviewer_{role}"),
    )
    agents.script("advisor_ui_ux", [responds_with(SpecialistAdvice(recommendations=["Stack the form below 600px."]))])
    agents.script("advisor_database", [responds_with(SpecialistAdvice(recommendations=["Give every record an id."]))])
    agents.script("principal_architect", [responds_with(_spec(
        interface_design=["Below 600px the form sits above the list."],
        specialist_advice_decisions=["UX-1: adopted - interface_design", "DB-1: adopted - data_model"],
    ))])
    agents.script("architecture_review", [responds_with(_approved_review())])
    agents.script("advice_reviewer_ui_ux", [responds_with(AdviceReview(not_built=["UX-1: no rule below 600px"]))])
    agents.script("advice_reviewer_database", [responds_with(AdviceReview(not_built=["DB-1: notes have no id"]))])
    _script_through_sprint(agents)


def test_the_reviews_run_side_by_side_and_all_reach_the_milestone_review(agents, monkeypatch, parallel, tmp_path, caplog):
    monkeypatch.setattr(workflow_module, "_changes_any_code", lambda files: True)
    _a_sprint_with_advice_reviews(agents, monkeypatch)
    caplog.set_level(logging.INFO, logger="app.graph.workflow")

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-reviews-side-by-side")

    assert state["stage"] == "complete", state.get("error")
    assert any(r.getMessage().startswith("Running 3 reviews side by side") for r in caplog.records)
    asked = agents.last_request_text("milestone_reviewer")
    assert "[UI/UX specialist] not built: UX-1: no rule below 600px" in asked
    assert "not built: DB-1: notes have no id" in asked
    assert state.get("security_review") is not None
    assert not state.get("reviews_in_flight")


def test_linear_mode_reviews_one_after_another(agents, monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(workflow_module, "_changes_any_code", lambda files: True)
    _a_sprint_with_advice_reviews(agents, monkeypatch)
    caplog.set_level(logging.INFO, logger="app.graph.workflow")

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-reviews-in-turn")

    assert state["stage"] == "complete", state.get("error")
    assert not any("side by side" in r.getMessage() for r in caplog.records)
    assert "not built: DB-1: notes have no id" in agents.last_request_text("milestone_reviewer")
