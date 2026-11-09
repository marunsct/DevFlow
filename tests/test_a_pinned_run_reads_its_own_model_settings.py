"""Inside a pinned run every read of the model settings is the run's own; everywhere else it is the settings page's.

The context window, the reply ceiling, the server profile, the endpoint probe on resume and the memos kept per server
all go through `effective_environment`, so a pinned run budgets and behaves for the model it is pinned to - and
the credential of the server the settings name is never carried to another server.
"""

from __future__ import annotations

import pytest

from app.models import model_pin
from app.server import runtime_settings

RUN = "the-run-under-test"
A = "http://127.0.0.1:8888/v1"
B = "http://127.0.0.1:1234/v1"


class _Store:
    def __init__(self):
        self.pinned = False
        self.last: dict[str, str] = {}

    def model_state(self, run_id):
        return (self.pinned, dict(self.last))

    def set_model_last(self, run_id, snapshot):
        if self.pinned:
            return False
        self.last = dict(snapshot)
        return True


@pytest.fixture
def world(monkeypatch):
    store = _Store()
    for name in ("OPENAI_API_KEY", "JUDGEMENT_MODEL", "JUDGEMENT_BASE_URL", "JUDGEMENT_PROVIDER",
                 "JUDGEMENT_API_KEY", "MODEL_MAX_OUTPUT_TOKENS", "OPENAI_ENDPOINT_KIND"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("OPENAI_BASE_URL", A)
    monkeypatch.setenv("OPENAI_MODEL", "model-a")
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "100000")
    monkeypatch.setattr(runtime_settings, "overrides", lambda **_: {})
    monkeypatch.setattr(runtime_settings, "secrets", lambda **_: {"openai_api_key": "key-of-a"})
    monkeypatch.setattr(runtime_settings, "endpoint_keys", lambda: {})
    monkeypatch.setattr(model_pin, "_store", lambda: store)
    monkeypatch.setattr(model_pin, "STATE_TTL_SECONDS", 0.0)
    model_pin.forget()
    store.snapshot_b = {"LLM_PROVIDER": "local", "OPENAI_BASE_URL": B, "OPENAI_MODEL": "model-b",
                        "MODEL_CONTEXT_WINDOW": "32768"}
    yield store
    model_pin.forget()


def test_without_a_pin_the_environment_is_the_settings_exactly(world):
    """Not pinned - or pinned to what the settings name - the environment is byte-for-byte what it was."""
    plain = runtime_settings.effective_environment(ignore_run=True)
    with model_pin.as_the_run(RUN):
        world.last = runtime_settings.global_model_snapshot()
        assert runtime_settings.effective_environment() == plain
        world.pinned = True
        assert runtime_settings.effective_environment() == plain
    assert plain["OPENAI_API_KEY"] == "key-of-a"


def test_a_pinned_run_sees_its_own_model_and_window_and_the_rest_of_the_world_sees_the_settings(world):
    """The run's snapshot is laid over the model keys; outside the run, and with ignore_run, nothing changes."""
    world.pinned, world.last = True, world.snapshot_b
    with model_pin.as_the_run(RUN):
        inside = runtime_settings.effective_environment()
        assert (inside["OPENAI_BASE_URL"], inside["OPENAI_MODEL"], inside["MODEL_CONTEXT_WINDOW"]) == (B, "model-b", "32768")
        assert runtime_settings.effective_environment(ignore_run=True)["OPENAI_MODEL"] == "model-a"
        from app.agents.context_budget import context_window

        assert context_window() == 32768
    assert runtime_settings.effective_environment()["OPENAI_MODEL"] == "model-a"
    assert runtime_settings.effective_environment(model=world.snapshot_b)["OPENAI_MODEL"] == "model-b"
    assert runtime_settings.effective_environment({"OPENAI_MODEL": "given"})["OPENAI_MODEL"] == "given"


def test_the_key_of_the_settings_server_is_not_carried_to_another_server(world, monkeypatch):
    """Pinned elsewhere, the provider-wide key is withheld; the server's own stored key is used, or none."""
    world.pinned, world.last = True, world.snapshot_b
    with model_pin.as_the_run(RUN):
        assert "OPENAI_API_KEY" not in runtime_settings.effective_environment()
    monkeypatch.setattr(runtime_settings, "endpoint_keys", lambda: {runtime_settings.endpoint_id("local", B): "key-of-b"})
    with model_pin.as_the_run(RUN):
        assert runtime_settings.effective_environment()["OPENAI_API_KEY"] == "key-of-b"
    assert runtime_settings.effective_environment(ignore_run=True)["OPENAI_API_KEY"] == "key-of-a"


def test_a_judgement_model_that_stays_where_it_was_keeps_its_key(world, monkeypatch):
    """Only the default model moved: the judgement model, on its own server, still has the key it had."""
    monkeypatch.setenv("JUDGEMENT_MODEL", "judge")
    monkeypatch.setenv("JUDGEMENT_BASE_URL", "http://127.0.0.1:9999/v1")
    world.pinned, world.last = True, {**world.snapshot_b, "JUDGEMENT_MODEL": "judge", "JUDGEMENT_BASE_URL": "http://127.0.0.1:9999/v1"}
    with model_pin.as_the_run(RUN):
        inside = runtime_settings.effective_environment()
    assert "OPENAI_API_KEY" not in inside
    assert inside["JUDGEMENT_API_KEY"] == "key-of-a"


def test_a_pin_to_an_explicit_endpoint_freezes_the_judgement_model_where_it_was():
    """A judgement model that shared the default server's address keeps it when only the default moves."""
    base = {"LLM_PROVIDER": "local", "OPENAI_BASE_URL": A, "OPENAI_MODEL": "m", "JUDGEMENT_MODEL": "judge",
            "JUDGEMENT_BASE_URL": "", "JUDGEMENT_PROVIDER": ""}
    pinned = model_pin.snapshot_for(base, B, "model-b")
    assert (pinned["OPENAI_BASE_URL"], pinned["OPENAI_MODEL"], pinned["JUDGEMENT_BASE_URL"]) == (B, "model-b", A)


def test_the_server_profile_is_read_again_when_the_run_moves_to_another_server(world, monkeypatch):
    """Moving the run to B does not wait out the five-minute throttle: the old server's slots are not B's."""
    from app.models import server_profile

    served = {A: server_profile.ServerProfile(slots=1, slot_context=100000),
              B: server_profile.ServerProfile(slots=2, slot_context=32768)}
    monkeypatch.setattr(server_profile, "read", lambda base, key="": served.get(base))
    server_profile.forget()
    with model_pin.as_the_run(RUN):
        server_profile.record()
        assert server_profile.check_again(RUN, clock=lambda: 1.0) == ""
        world.pinned, world.last = True, world.snapshot_b
        noticed = server_profile.check_again(RUN, clock=lambda: 2.0)
    assert "slots 1 -> 2" in noticed
    assert server_profile.current().slots == 2
    server_profile.forget()


def test_memos_kept_per_server_follow_the_server_the_run_is_on(world):
    """What was learned of server A (a refused tool choice, a reply ceiling) is looked up under B for a run pinned to B."""
    from app.models import build_default_chat_model

    with model_pin.as_the_run(RUN):
        client = build_default_chat_model()
        assert client._served_by() == (A, "model-a")
        world.pinned, world.last = True, world.snapshot_b
        assert client._served_by() == (B, "model-b")
        world.pinned = False
        assert client._served_by() == (A, "model-a")


@pytest.mark.real_endpoint_probe
def test_resuming_a_pinned_run_probes_the_model_it_will_use(world, monkeypatch):
    """The API checks the endpoint the pinned run is on, not the one the settings name."""
    from app.models import endpoint_probe
    from app.server.runner import WorkflowRunner

    probed = []

    class _Up:
        reachable = True
        detail = ""

    monkeypatch.setattr(endpoint_probe, "describe_model_endpoint", lambda settings: probed.append(settings.openai_base_url) or _Up())
    world.pinned, world.last = True, world.snapshot_b
    WorkflowRunner._require_a_reachable_model(None, RUN)
    WorkflowRunner._require_a_reachable_model(None, None)
    assert probed == [B, A]
