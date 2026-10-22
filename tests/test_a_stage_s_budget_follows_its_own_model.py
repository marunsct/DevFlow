"""Context budgets follow the settings page, and each stage's follows its own model's window.

Measured in one worker: the settings page gave the default model a
130,000-token window and the judgement model 1,000,000, but every budget -
when a conversation is compacted, how much of a document a stage is shown,
the default model's reply ceiling - was derived from the process
environment's 100,000. The judgement stages compacted their conversations at
the default model's size.
"""

from __future__ import annotations

import pytest

from app.agents.context_budget import ContextBudget, context_window

BASE = {
    "LLM_PROVIDER": "local",
    "OPENAI_BASE_URL": "http://localhost:8888/v1",
    "OPENAI_MODEL": "build-model",
    "OPENAI_API_KEY": "local-placeholder",
    "MODEL_CONTEXT_WINDOW": "130000",
    "JUDGEMENT_MODEL": "frontier-model",
    "JUDGEMENT_BASE_URL": "https://frontier.example/v1",
    "JUDGEMENT_CONTEXT_WINDOW": "1000000",
}


@pytest.fixture
def settings_differ_from_the_process(monkeypatch):
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "100000")
    monkeypatch.setattr("app.server.runtime_settings.effective_environment", lambda *a, **k: dict(BASE))


def test_the_budget_follows_the_settings_page(settings_differ_from_the_process):
    assert context_window() == 130_000
    assert ContextBudget.resolve().window_tokens == 130_000


@pytest.fixture
def triggers(monkeypatch):
    """The compaction threshold each built middleware was given, in tokens."""
    seen: list[int] = []

    def record(model, **kwargs):
        seen.append(kwargs["trigger"][1])
        return object()

    monkeypatch.setattr("app.agents.role_agent.RequestKeepingSummarization", record)
    return seen


def test_a_judgement_stage_compacts_at_its_own_model_s_size(settings_differ_from_the_process, triggers):
    from app.agents.role_agent import _compaction_middleware
    from app.models import environment_of
    from app.models.roles import build_judgement_model

    frontier = build_judgement_model("default", dict(BASE))
    assert environment_of(frontier)["MODEL_CONTEXT_WINDOW"] == "1000000"

    _compaction_middleware("principal_architect", frontier)
    _compaction_middleware("principal_architect", None)
    own, default = triggers

    from app.agents.context_policy import ContextPolicy

    assert default == ContextPolicy.from_environment(dict(BASE)).trigger_tokens
    assert own > 5 * default


def test_a_model_built_from_the_deployment_s_environment_has_none_of_its_own():
    from app.models import environment_of

    assert environment_of(object()) is None
