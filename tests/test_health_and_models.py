"""Health endpoints and the chat-model factory."""

import pytest


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_liveness_is_cheap_and_always_ok(client):
    """Split from readiness so a transient dependency blip restarts nothing."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_every_dependency(client):
    response = client.get("/api/health/ready")
    body = response.json() if response.status_code == 200 else response.json()["detail"]
    assert set(body) >= {"status", "db", "redis", "celery"}


def test_readiness_fails_when_celery_has_no_workers(client, monkeypatch):
    """`control.ping()` returns [] rather than raising, so the previous
    try/except could never report Celery as down."""
    from app.server.tasks import celery_app

    monkeypatch.setattr(celery_app.control, "ping", lambda timeout=1.0: [])

    response = client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["celery"] == "error"


def test_readiness_passes_when_a_worker_answers(client, monkeypatch):
    from app.server.tasks import celery_app

    monkeypatch.setattr(celery_app.control, "ping", lambda timeout=1.0: [{"celery@host": "pong"}])

    response = client.get("/api/health/ready")
    assert response.json().get("celery") == "ok"


def test_readiness_fails_when_redis_is_unreachable(client, monkeypatch):
    from app.server.tasks import celery_app

    monkeypatch.setattr(celery_app.control, "ping", lambda timeout=1.0: [{"w": "pong"}])

    class _Broken:
        async def ping(self):
            raise ConnectionError("redis down")

    monkeypatch.setattr("app.server.redis_client.get_async_redis_client", lambda: _Broken())

    response = client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["redis"] == "error"


def test_model_health_is_reachable_for_an_admin(client):
    response = client.get("/api/health/models")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Chat-model factory
# ---------------------------------------------------------------------------


def test_fallback_models_come_from_configuration(monkeypatch):
    from app.models import _fallback_model

    monkeypatch.delenv("ANTHROPIC_FALLBACK_MODEL", raising=False)
    assert _fallback_model("ANTHROPIC_FALLBACK_MODEL", "claude-haiku-4-5-20251001") == (
        "claude-haiku-4-5-20251001"
    )

    monkeypatch.setenv("ANTHROPIC_FALLBACK_MODEL", "claude-sonnet-5")
    assert _fallback_model("ANTHROPIC_FALLBACK_MODEL", "unused") == "claude-sonnet-5"


def test_an_empty_override_falls_back_to_the_default(monkeypatch):
    from app.models import _fallback_model

    monkeypatch.setenv("OPENAI_FALLBACK_MODEL", "   ")
    assert _fallback_model("OPENAI_FALLBACK_MODEL", "gpt-4o-mini") == "gpt-4o-mini"


def test_the_local_provider_builds_an_openai_compatible_client(monkeypatch):
    from app.config import load_settings
    from app.models import build_default_chat_model
    from app.models.router import ModelRouter

    ModelRouter.reset()
    settings = load_settings(
        {
            "LLM_PROVIDER": "local",
            "OPENAI_BASE_URL": "http://localhost:1234/v1",
            "OPENAI_API_KEY": "lm-studio",
            "OPENAI_MODEL": "local-model",
        }
    )
    model = build_default_chat_model(settings)
    assert model is not None
    ModelRouter.reset()


def test_two_providers_do_not_share_a_router(monkeypatch):
    """Regression for the process-wide singleton that every run overwrote."""
    from app.config import load_settings
    from app.models import build_default_chat_model
    from app.models.router import ModelRouter

    ModelRouter.reset()
    build_default_chat_model(
        load_settings({"LLM_PROVIDER": "local", "OPENAI_BASE_URL": "http://a:1/v1", "OPENAI_MODEL": "m1"})
    )
    build_default_chat_model(
        load_settings({"LLM_PROVIDER": "local", "OPENAI_BASE_URL": "http://b:2/v1", "OPENAI_MODEL": "m2"})
    )

    assert len(ModelRouter.all_routers()) == 2
    ModelRouter.reset()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_gemini_key_alias_is_accepted():
    """docker-compose and .env.example both set GEMINI_API_KEY, while the code
    read only GOOGLE_API_KEY - so Gemini never received a key."""
    from app.config import load_settings

    settings = load_settings({"GEMINI_API_KEY": "aiza-test", "OPENAI_MODEL": "m"})
    assert settings.google_api_key == "aiza-test"


def test_the_canonical_google_key_wins_over_the_alias():
    from app.config import load_settings

    settings = load_settings(
        {"GOOGLE_API_KEY": "canonical", "GEMINI_API_KEY": "alias", "OPENAI_MODEL": "m"}
    )
    assert settings.google_api_key == "canonical"


def test_the_checkpointer_default_is_shared_across_processes():
    """memory and sqlite are both per-process; the API and worker need one store."""
    from app.config import DEFAULT_CHECKPOINTER, load_settings

    assert DEFAULT_CHECKPOINTER == "postgres"
    assert load_settings({"OPENAI_MODEL": "m"}).checkpointer_type == "postgres"


@pytest.mark.parametrize("value", ["true", "yes", "on", "1"])
def test_truthy_booleans_are_parsed(value):
    from app.config import load_settings

    assert load_settings({"WORKFLOW_REQUIRE_APPROVAL": value, "OPENAI_MODEL": "m"}).require_approval


def test_an_unparseable_boolean_is_rejected():
    from app.config import ConfigurationError, load_settings

    with pytest.raises(ConfigurationError):
        load_settings({"WORKFLOW_REQUIRE_APPROVAL": "perhaps", "OPENAI_MODEL": "m"})


def _llm_result(llm_output, usage_metadata):
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    message = AIMessage(content="hi")
    if usage_metadata is not None:
        message.usage_metadata = usage_metadata
    return LLMResult(generations=[[ChatGeneration(message=message)]], llm_output=llm_output)


def test_the_cost_tracker_counts_an_unstreamed_response() -> None:
    from app.observability.cost_tracker import CostTrackingCallbackHandler

    tracker = CostTrackingCallbackHandler("cost-unstreamed", provider="openai", model="gpt-4o-mini")
    tracker.on_llm_end(
        _llm_result({"token_usage": {"prompt_tokens": 19, "completion_tokens": 10, "total_tokens": 29}}, None)
    )

    assert tracker.get_summary()["total_tokens"] == 29


def test_the_cost_tracker_counts_a_streamed_response() -> None:
    """A streamed response leaves `llm_output` empty and carries usage on the message.

    Reading only `llm_output` reported zero tokens for every call in a run
    once the models began streaming - verified against the local server, which
    counted 19 prompt and 10 completion tokens unstreamed and 0 and 0 streamed.
    """
    from app.observability.cost_tracker import CostTrackingCallbackHandler

    tracker = CostTrackingCallbackHandler("cost-streamed", provider="openai", model="gpt-4o-mini")
    tracker.on_llm_end(
        _llm_result(None, {"input_tokens": 19, "output_tokens": 10, "total_tokens": 29})
    )

    summary = tracker.get_summary()
    assert summary["prompt_tokens"] == 19
    assert summary["completion_tokens"] == 10
    assert summary["total_tokens"] == 29


def test_a_response_with_no_usage_anywhere_is_counted_as_a_request_only() -> None:
    """It must not invent numbers, and must not raise."""
    from app.observability.cost_tracker import CostTrackingCallbackHandler

    tracker = CostTrackingCallbackHandler("cost-no-usage", provider="openai", model="gpt-4o-mini")
    tracker.on_llm_end(_llm_result(None, None))

    summary = tracker.get_summary()
    assert summary["successful_requests"] == 1
    assert summary["total_tokens"] == 0
