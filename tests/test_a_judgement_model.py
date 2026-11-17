"""The judgement model: the stages that judge run on it, everything else on the default.

See `app.models.roles`. With nothing configured every stage runs on the default
model, as before; a configured name builds a second model from the default
model's settings with only what was set replaced.
"""

from __future__ import annotations

import pytest

from app.models.roles import build_judgement_model, judgement_environment
from test_graph_routing import agents  # noqa: F401 - `agents` is a fixture

BASE = {
    "LLM_PROVIDER": "local",
    "OPENAI_BASE_URL": "http://host:1234/v1",
    "OPENAI_MODEL": "small-model",
    "OPENAI_API_KEY": "local-key",
    "MODEL_CONTEXT_WINDOW": "32000",
    "MODEL_MAX_OUTPUT_TOKENS": "8000",
}


def test_nothing_configured_means_no_second_model() -> None:
    assert judgement_environment(BASE) is None
    default = object()
    assert build_judgement_model(default, BASE) is default


def test_a_name_alone_reuses_everything_else() -> None:
    built = judgement_environment({**BASE, "JUDGEMENT_MODEL": "big-model"})
    assert built["OPENAI_MODEL"] == "big-model"
    assert built["OPENAI_BASE_URL"] == "http://host:1234/v1"
    assert built["LLM_PROVIDER"] == "local"
    assert built["MODEL_CONTEXT_WINDOW"] == "32000"


def test_its_own_provider_address_key_and_window() -> None:
    built = judgement_environment({
        **BASE,
        "JUDGEMENT_MODEL": "claude-opus-5-5",
        "JUDGEMENT_PROVIDER": "anthropic",
        "JUDGEMENT_BASE_URL": "https://example.invalid/v1",
        "JUDGEMENT_API_KEY": "judge-key",
        "JUDGEMENT_CONTEXT_WINDOW": "200000",
    })
    assert built["LLM_PROVIDER"] == "anthropic"
    assert built["ANTHROPIC_API_KEY"] == "judge-key"
    # The default model's key is untouched; the judgement key went to its provider's slot.
    assert built["OPENAI_API_KEY"] == "local-key"
    assert built["MODEL_CONTEXT_WINDOW"] == "200000"
    # A reply ceiling pinned for the small model is not carried to a different window.
    assert "MODEL_MAX_OUTPUT_TOKENS" not in built


def test_a_model_that_cannot_be_built_falls_back_to_the_default(monkeypatch) -> None:
    def broken(settings):
        raise RuntimeError("no such provider")

    monkeypatch.setattr("app.models.build_default_chat_model", broken)
    default = object()
    assert build_judgement_model(default, {**BASE, "JUDGEMENT_MODEL": "big-model"}) is default


def test_a_configured_model_is_built_from_its_own_settings(monkeypatch) -> None:
    seen = []
    monkeypatch.setattr("app.models.build_default_chat_model", lambda settings, environment=None: seen.append(settings) or "built")
    assert build_judgement_model(object(), {**BASE, "JUDGEMENT_MODEL": "big-model"}) == "built"
    assert seen[0].model_name == "big-model"


def _on_two_models(monkeypatch):
    """A graph on a build model and a distinct judgement model, recording which model each agent was built with."""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langgraph.checkpoint.memory import MemorySaver

    from app.graph import workflow
    from app.graph.checkpointing import build_serializer

    build = FakeListChatModel(responses=["unused"], name="build")
    judge = FakeListChatModel(responses=["unused"], name="judge")
    monkeypatch.setattr("app.models.roles.build_judgement_model", lambda model, *a, **k: judge)
    seen: list[tuple[str, str]] = []

    def recording(factory_name, role_of):
        original = getattr(workflow, factory_name)

        def build_agent(*args, **kwargs):
            seen.append((role_of(args, kwargs), getattr(kwargs.get("model"), "name", "?")))
            return original(*args, **kwargs)

        monkeypatch.setattr(workflow, factory_name, build_agent)

    recording("create_specialist_agent", lambda a, k: f"specialist_{a[0]}")
    for factory, role in (
        ("create_principal_architect_agent", "principal_architect"),
        ("create_architecture_reviewer_agent", "architecture_review"),
        ("create_security_reviewer_agent", "security_review"),
        ("create_milestone_reviewer_agent", "milestone_review"),
    ):
        recording(factory, lambda a, k, role=role: role)
    return workflow.build_workflow_graph(model=build, checkpointer=MemorySaver(serde=build_serializer())), seen


def test_the_judging_stages_run_on_it(agents, monkeypatch, tmp_path) -> None:
    """The architect, the reviews and the test rounds run on the judgement model; a work order on the build model.

    The fixes run on the build model until they have failed, then on this one: see `test_two_model_tiers`.
    """
    from test_graph_routing import (
        _approved_review, _document, _milestone, _milestone_review, _repository, _script_through_architecture,
        _security_review, _specialist, _sprint_plan, responds_with,
    )

    from app.graph import workflow

    graph, seen = _on_two_models(monkeypatch)
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script("specialist_backend", [responds_with(_specialist())])
    agents.script("specialist_testing", [responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = workflow.start_workflow(graph, _document(), _repository(tmp_path), "run-judging-stages")

    assert state["stage"] == "complete", state.get("error")
    # A sprint whose changes no conversation wrote has no code to review for security: asked of its node directly.
    from types import SimpleNamespace
    from unittest.mock import patch

    from app.agents.specialists import SpecialistOutput

    with patch("app.graph.workflow._in_parallel_mode", return_value=False), \
         patch("app.graph.workflow._run_gated_agent", return_value={"stage": "security_review"}):
        graph.nodes["security_review"].bound.invoke(
            {"repository": SimpleNamespace(root_path=str(tmp_path)),
             "specialist_outputs": {"specialist_backend_0": SpecialistOutput(changed_files=["app/server.py"])}},
            {"configurable": {"thread_id": "t", "run_id": "r"}})
    for judging in ("principal_architect", "architecture_review", "security_review", "milestone_review",
                    "specialist_testing"):
        assert (judging, "judge") in seen and (judging, "build") not in seen, judging
    assert ("specialist_backend", "build") in seen, "the work order is built on the build model"


def test_a_fix_in_a_batch_runs_on_the_build_model_until_it_has_failed(monkeypatch, tmp_path) -> None:
    """A batch's fixer is chosen as a fix alone is: the build model, and the judgement model once its fixes failed."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from app.models.roles import escalate_after
    from app.sprint import Defect, RemediationCycle

    graph, seen = _on_two_models(monkeypatch)

    def the_fixer_s_model(fix_attempts: int) -> str:
        seen.clear()
        defect = Defect(description="The count is wrong", severity="major", reproduction_steps="r",
                        expected_behavior="e", actual_behavior="a", owner="backend", fix_attempts=fix_attempts)
        state = {"__fix_index": 0, "remediation": RemediationCycle(sprint_goal="g", defects=[defect]),
                 "test_round": 1, "repository": SimpleNamespace(root_path=str(tmp_path))}
        with patch("app.graph.workflow.build_defect_fix_request", return_value={"messages": [{"role": "user", "content": ""}]}), \
             patch("app.graph.workflow._what_the_last_failure_printed", return_value=""), \
             patch("app.graph.workflow._run_gated_agent", return_value={"__fix_result__": MagicMock()}):
            graph.nodes["defect_fix_worker"].bound.invoke(state, {"configurable": {"thread_id": "t", "run_id": "r"}})
        [(role, model)] = seen
        assert role == "specialist_backend"
        return model

    assert the_fixer_s_model(0) == "build"
    assert the_fixer_s_model(escalate_after()) == "judge"


@pytest.fixture
def _clean_runtime_settings(test_db):
    from app.server import runtime_settings

    runtime_settings.reset_cache()
    runtime_settings.clear()
    runtime_settings.clear_secrets()
    yield
    runtime_settings.clear()
    runtime_settings.clear_secrets()
    runtime_settings.reset_cache()


def test_the_settings_page_sets_and_clears_it(client, _clean_runtime_settings) -> None:
    from app.server import runtime_settings

    response = client.put("/api/settings", json={
        "llm_provider": "local",
        "openai_base_url": "http://host:1234/v1",
        "model_name": "small-model",
        "judgement_model_name": "big-model",
        "judgement_provider": "openai",
        "judgement_base_url": "https://api.openai.com/v1",
        "judgement_context_window": 128000,
        "judgement_api_key": "sk-judge-secret-9876",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["judgement_model_name"] == "big-model"
    assert body["judgement_context_window"] == 128000
    assert body["judgement_api_key_configured"] is True
    assert "sk-judge-secret-9876" not in str(body)
    assert runtime_settings.effective_environment()["JUDGEMENT_MODEL"] == "big-model"

    # A general save that names no frontier model leaves it as it is: it has its own section and its own
    # "No model". Measured: a general save six seconds after a frontier save wiped the frontier model.
    kept = client.put("/api/settings", json={
        "llm_provider": "local",
        "openai_base_url": "http://host:1234/v1",
        "model_name": "small-model",
        "judgement_model_name": "",
        "judgement_provider": "",
        "judgement_base_url": "",
    }).json()
    assert kept["judgement_model_name"] == "big-model"

    cleared = client.put("/api/settings/frontier", json={
        "judgement_provider": "", "judgement_base_url": "", "judgement_model_name": "",
        "judgement_context_window": 0, "judgement_max_output_tokens": 0,
        "escalate_after_attempts": 2, "plan_on_judgement_model": False, "no_model": True,
    }).json()
    assert cleared["judgement_model_name"] == ""


def test_an_unknown_judgement_provider_is_rejected(client, _clean_runtime_settings) -> None:
    response = client.put("/api/settings", json={
        "llm_provider": "local",
        "openai_base_url": "http://host:1234/v1",
        "model_name": "small-model",
        "judgement_model_name": "big-model",
        "judgement_provider": "no-such-provider",
    })
    assert response.status_code == 422
