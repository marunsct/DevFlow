"""Model routing: per-configuration scoping, health tracking and fallbacks."""

import pytest

from app.models.router import ModelRouter, get_router_status


class _StubModel:
    """A chat-model stand-in that can be told to fail."""

    def __init__(self, name: str, healthy: bool = True):
        self.name = name
        self.healthy = healthy
        self.fallbacks: list = []
        self.pings = 0

    def invoke(self, _messages, config=None):
        self.pings += 1
        if not self.healthy:
            raise RuntimeError(f"{self.name} is unavailable")
        return "pong"

    def with_fallbacks(self, fallbacks):
        self.fallbacks = list(fallbacks)
        return self


class _Settings:
    def __init__(self, provider="openai", base_url="https://api.openai.com/v1", model="gpt-4o"):
        self.llm_provider = provider
        self.openai_base_url = base_url
        self.model_name = model


@pytest.fixture(autouse=True)
def clean_registry():
    ModelRouter.reset()
    yield
    ModelRouter.reset()


def _models(*specs):
    return [{"name": name, "model": _StubModel(name, healthy)} for name, healthy in specs]


# ---------------------------------------------------------------------------
# Per-configuration scoping
# ---------------------------------------------------------------------------


def test_the_same_configuration_reuses_one_router():
    first = ModelRouter.for_configuration(_Settings(), _models(("primary", True)))
    second = ModelRouter.for_configuration(_Settings(), _models(("primary", True)))
    assert first is second


def test_different_configurations_get_different_routers():
    """Two runs with different providers used to overwrite each other's models."""
    openai_router = ModelRouter.for_configuration(
        _Settings(provider="openai"), _models(("openai", True))
    )
    local_router = ModelRouter.for_configuration(
        _Settings(provider="local", base_url="http://localhost:1234/v1"),
        _models(("local", True)),
    )

    assert openai_router is not local_router
    assert openai_router.status() == {"openai": "healthy"}
    assert local_router.status() == {"local": "healthy"}


def test_the_configuration_key_excludes_secrets():
    key = ModelRouter.configuration_key(_Settings())
    assert "openai" in key
    assert "sk-" not in key


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_is_preserved_across_a_model_reinstall():
    """set_models runs on every agent construction; it must not reset health."""
    router = ModelRouter("test")
    models = _models(("primary", False))
    router.set_models(models)
    router.check_health(force=True)
    assert router.status()["primary"] == "unhealthy"

    router.set_models(models)
    assert router.status()["primary"] == "unhealthy"


def test_health_checks_are_throttled():
    router = ModelRouter("test")
    model = _StubModel("primary")
    router.set_models([{"name": "primary", "model": model}])

    router.check_health(force=True)
    router.check_health()  # inside the interval, so skipped
    assert model.pings == 1


def test_getting_a_model_does_not_ping_it():
    """An inline ping would add a round trip to every graph node."""
    router = ModelRouter("test")
    model = _StubModel("primary")
    router.set_models([{"name": "primary", "model": model}])

    router.get_healthy_model()
    assert model.pings == 0


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def test_a_single_model_is_returned_directly():
    router = ModelRouter("test")
    router.set_models(_models(("primary", True)))
    assert router.get_healthy_model().name == "primary"


def test_remaining_models_become_fallbacks():
    router = ModelRouter("test")
    router.set_models(_models(("primary", True), ("backup", True)))

    selected = router.get_healthy_model()
    assert selected.name == "primary"
    assert [m.name for m in selected.fallbacks] == ["backup"]


def test_an_unhealthy_primary_is_skipped():
    router = ModelRouter("test")
    router.set_models(_models(("primary", False), ("backup", True)))
    router.check_health(force=True)

    assert router.get_healthy_model().name == "backup"


def test_the_primary_is_tried_even_when_everything_looks_unhealthy():
    """Failing the run outright is worse than one more attempt."""
    router = ModelRouter("test")
    router.set_models(_models(("primary", False), ("backup", False)))
    router.check_health(force=True)

    assert router.get_healthy_model().name == "primary"


def test_asking_for_a_model_before_any_are_configured_raises():
    router = ModelRouter("test")
    with pytest.raises(ValueError, match="No models"):
        router.get_healthy_model()


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------


def test_status_reports_every_configured_router():
    ModelRouter.for_configuration(_Settings(provider="openai"), _models(("openai", True)))
    ModelRouter.for_configuration(
        _Settings(provider="anthropic", base_url="https://api.anthropic.com"),
        _models(("anthropic", False)),
    )

    status = get_router_status()
    flattened = {name: state for group in status.values() for name, state in group.items()}
    assert flattened["openai"] == "healthy"
    assert flattened["anthropic"] == "unhealthy"


def test_status_is_informative_when_nothing_is_configured():
    assert "detail" in get_router_status()


# ---------------------------------------------------------------------------
# Output ceiling
# ---------------------------------------------------------------------------


def test_a_model_turn_is_bounded_by_the_context_window() -> None:
    """Unbounded, one turn burned 108,000 tokens and 38 minutes on run-0b55ad49."""
    from app.agents.context_budget import ContextBudget
    from app.models import _max_output_tokens

    assert _max_output_tokens() == ContextBudget.resolve().max_output_tokens
    # Above the largest legitimate write (a 51 KB specification, ~13k tokens)
    # and far below the observed runaway.
    assert 13_000 < _max_output_tokens() < 108_000


def test_the_reply_ceiling_follows_the_window(monkeypatch) -> None:
    """A bigger model gets a bigger allowance without anyone retuning it."""
    from app.models import _max_output_tokens

    monkeypatch.delenv("MODEL_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "40000")
    small = _max_output_tokens()
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "262144")
    large = _max_output_tokens()

    assert small < large


def test_the_ceiling_is_configurable(monkeypatch) -> None:
    from app.models import _max_output_tokens

    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", "50000")
    assert _max_output_tokens() == 50_000


def test_a_ceiling_too_low_to_write_an_artifact_is_raised(monkeypatch) -> None:
    """Truncating a write_artifact call mid-document corrupts the file.

    An override is a deliberate exception, not a licence to break the floor.
    """
    from app.models import _max_output_tokens

    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", "10")
    assert _max_output_tokens() >= 4_000


def test_a_malformed_ceiling_falls_back_to_the_derived_value(monkeypatch) -> None:
    from app.agents.context_budget import ContextBudget
    from app.models import _max_output_tokens

    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", "lots")
    monkeypatch.delenv("MODEL_CONTEXT_WINDOW", raising=False)
    assert _max_output_tokens() == ContextBudget.from_window(
        ContextBudget.resolve().window_tokens
    ).max_output_tokens
