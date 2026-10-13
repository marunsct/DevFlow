"""Two model tiers: the judgement model plans, the default model builds, and a failure escalates.

The owner's configuration: a fast local model writes the code from a plan a
frontier model wrote in full detail, and whatever the local model could not
do in `escalate_after()` tries (2) goes to the frontier model - a work order
whose stage had to start over that often, or a defect whose fixes failed that
often. If the frontier model fails too, the run goes on as before.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.checkpoint.memory import MemorySaver

from app.graph import workflow
from app.graph.checkpointing import build_serializer
from app.models.roles import escalate_after, plans_on_the_judgement_model
from app.sprint import failed_fix_tries
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    _approved_review,
    _defect,
    _document,
    _milestone,
    _milestone_review,
    _repository,
    _script_through_architecture,
    _security_review,
    _specialist,
    _sprint_plan,
    agents,
    responds_with,
)

BUILD = FakeListChatModel(responses=["unused"], name="build")
JUDGE = FakeListChatModel(responses=["unused"], name="judge")


@pytest.fixture
def tiers(monkeypatch, agents):
    """A graph on two distinct models, recording which one each agent was built with."""
    monkeypatch.setattr("app.models.roles.build_judgement_model", lambda model, *a, **k: JUDGE)
    seen: list[tuple[str, str]] = []

    def recording(factory_name: str, role_of):
        original = getattr(workflow, factory_name)

        def build(*args, **kwargs):
            seen.append((role_of(args, kwargs), getattr(kwargs.get("model"), "name", "?")))
            return original(*args, **kwargs)

        monkeypatch.setattr(workflow, factory_name, build)

    recording("create_specialist_agent", lambda a, k: f"specialist_{a[0]}")
    for factory, role in (
        ("create_product_manager_agent", "product_manager"), ("create_tools_models_agent", "tools_models"),
        ("create_stack_selector_agent", "stack_selector"), ("create_scrum_master_agent", "scrum_master"),
        ("create_technical_lead_agent", "technical_lead"),
    ):
        recording(factory, lambda a, k, role=role: role)
    graph = workflow.build_workflow_graph(model=BUILD, checkpointer=MemorySaver(serde=build_serializer()))
    return SimpleNamespace(graph=graph, seen=seen)


def test_the_planning_stages_run_on_the_judgement_model(tiers, agents, tmp_path):
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script("specialist_backend", [responds_with(_specialist())])
    agents.script("specialist_testing", [responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = workflow.start_workflow(tiers.graph, _document(), _repository(tmp_path), "run-tiers-plan")

    assert state["stage"] == "complete", state.get("error")
    models = dict(tiers.seen)
    for planner in ("product_manager", "tools_models", "stack_selector", "scrum_master", "technical_lead"):
        assert models[planner] == "judge", planner
    assert ("specialist_backend", "build") in tiers.seen, "the work order is built on the build model"


def test_a_defect_whose_fix_failed_goes_to_the_judgement_model(tiers, agents, tmp_path, monkeypatch):
    """With `escalate_after()` at 1: the first fix on the build model, the next on the judgement model.

    At the default 2 the second failed round ends the sprint's attempt first,
    and a re-planned sprint is built on the judgement model anyway
    (`_the_model_for_this_attempt`).
    """
    monkeypatch.setenv("ESCALATE_AFTER_ATTEMPTS", "1")
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    # The work order, a fix that names no regression test (left open), then one that does.
    agents.script("specialist_backend", [
        responds_with(_specialist()), responds_with(_specialist()), responds_with(_specialist(tests=["t-fixed"])),
    ])
    agents.script("specialist_testing", [responds_with(_specialist(defects=[_defect()]))] + [responds_with(_specialist())] * 4)
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = workflow.start_workflow(tiers.graph, _document(), _repository(tmp_path), "run-tiers-escalate")

    assert state["stage"] == "complete", state.get("error")
    backend = [model for role, model in tiers.seen if role == "specialist_backend"]
    assert backend == ["build", "build", "judge"], backend
    assert state["remediation"].defects[0].regression_test == "t-fixed"
    assert state["remediation"].defects[0].fix_attempts == 1


def test_a_recurring_defect_counts_the_fix_that_did_not_hold():
    fixed = SimpleNamespace(description="Notes API returns 500 on save", status="fixed", fix_attempts=1)
    back = SimpleNamespace(description="Notes API returns 500 when saving", status="open", fix_attempts=0)
    cycle = SimpleNamespace(defects=[fixed, back])

    assert failed_fix_tries(cycle, 1) == 2
    assert failed_fix_tries(cycle, 0) == 1


def test_the_settings_and_their_defaults():
    assert escalate_after({}) == 2 and escalate_after({"ESCALATE_AFTER_ATTEMPTS": "3"}) == 3
    assert escalate_after({"ESCALATE_AFTER_ATTEMPTS": "0"}) == 1
    assert plans_on_the_judgement_model({}) is True
    assert plans_on_the_judgement_model({"PLAN_ON_JUDGEMENT_MODEL": "false"}) is False


def test_the_settings_page_saves_both(test_db):
    from app.server import runtime_settings
    from app.server.settings import SettingsUpdate

    assert {"escalate_after_attempts", "plan_on_judgement_model"} <= set(runtime_settings.SETTABLE_KEYS)
    update = SettingsUpdate(llm_provider="local", openai_base_url="http://x/v1", model_name="m",
                            escalate_after_attempts=3, plan_on_judgement_model=False)
    assert update.escalate_after_attempts == 3 and update.plan_on_judgement_model is False
