"""The judgement model: the stages that judge run on it, everything else on the default.

See `app.models.roles`. With nothing configured every stage runs on the default
model, as before; a configured name builds a second model from the default
model's settings with only what was set replaced.
"""

from __future__ import annotations

import pytest

from app.models.roles import build_judgement_model, judgement_environment

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


def test_the_judging_stages_run_on_it() -> None:
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow.build_workflow_graph)
    for factory in (
        "create_principal_architect_agent",
        "create_architecture_reviewer_agent",
        "create_security_reviewer_agent",
        "create_milestone_reviewer_agent",
    ):
        assert f"{factory}(model=judgement_model" in source, factory
    # The test rounds. The fixes run on the build model until they have
    # failed, then on this one: see `test_two_model_tiers`.
    assert '"testing", model=judgement_model' in source
    assert "defect.owner, model=_the_build_model(" in source


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
