"""A model's measured speed sets how long its calls are waited for; what two requests at once really get sets the
parallel cap and the balancer's session scope (DX.6).

Nothing measured these before: the timeout floor was 30 tokens a second whatever the model (the newest runs at a
median of 62, a slower one would be cut off), and two one-slot servers behind a balancer queued both runs'
conversations on one server while the other sat idle, the cap being the slots whatever they gave.
"""
from __future__ import annotations

import pytest

from app import models
from app.graph.workflow import concurrent_requests
from app.models import capabilities, server_profile, steering_job
from app.models.session_header import session_scope
from tests.diagnosis_fakes import Balanced, Everything, model

ADDRESS = "http://model-server:2001/v1"
NAME = "a-model.gguf"


@pytest.fixture(autouse=True)
def _a_fresh_deployment(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path / "gate"))
    monkeypatch.setenv("OPENAI_BASE_URL", ADDRESS)
    monkeypatch.setenv("MODEL_NAME", NAME)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    for name in ("MODEL_SESSION_SCOPE", "MODEL_TOKENS_PER_SECOND", "HARNESS_MAX_PARALLEL", "PROFILE_FROM_DIAGNOSIS"):
        monkeypatch.delenv(name, raising=False)
    # The model card lookups reach the internet; they are not what is measured here.
    monkeypatch.setattr(capabilities, "fill", lambda *a, **k: {})
    server_profile.forget()
    yield
    server_profile.forget()
    try:
        from app.models import diagnosis_profile

        diagnosis_profile.forget()
    except ImportError:
        pass


def _diagnosed_on(monkeypatch, server, slots: int = 2) -> None:
    """The settings page's diagnosis, run against `server`, which says it serves `slots` requests at once."""
    found = server_profile.ServerProfile(slots=slots, model=NAME)
    monkeypatch.setattr(server_profile, "read", lambda *args, **kwargs: found)
    monkeypatch.setattr(models, "build_default_chat_model", lambda *a, **k: model(server, name=NAME, base=ADDRESS))
    steering_job.run()
    assert steering_job.status()["status"] == "idle", steering_job.status()


def test_a_slow_model_is_waited_for_as_long_as_its_measured_speed_needs(monkeypatch):
    """20 tokens a second: the largest legitimate reply, 13,000 tokens, needs 650 s, not the 433 s of 30 a second."""
    _diagnosed_on(monkeypatch, Balanced(Everything(), rate=20.0, seconds=0.0))

    assert models._tokens_per_second() == 20.0
    assert models._request_timeout() >= 650


def test_a_fast_model_keeps_the_default_floor(monkeypatch):
    """A floor only ever lowered: 90 tokens a second measured leaves 30, so no call is cut off sooner."""
    _diagnosed_on(monkeypatch, Balanced(Everything(), rate=90.0, seconds=0.0))

    assert models._tokens_per_second() == models.DEFAULT_MIN_TOKENS_PER_SECOND


def test_two_conversations_that_land_on_one_server_make_sessions_per_request(monkeypatch):
    """The balancer kept both conversations on the first server; fresh sessions spread over both."""
    monkeypatch.setenv("PROFILE_FROM_DIAGNOSIS", "on")
    _diagnosed_on(monkeypatch, Balanced(Everything(), servers=2, slots=1))

    assert session_scope() == "request"
    assert concurrent_requests() == 2


def test_the_owner_s_session_scope_wins_over_the_measured_one(monkeypatch):
    monkeypatch.setenv("PROFILE_FROM_DIAGNOSIS", "on")
    monkeypatch.setenv("MODEL_SESSION_SCOPE", "conversation")
    _diagnosed_on(monkeypatch, Balanced(Everything(), servers=2, slots=1))

    assert session_scope() == "conversation"


def test_a_second_slot_that_adds_nothing_holds_the_parallel_cap_at_one(monkeypatch):
    """The server says two slots but answers one request at a time: two at once take twice as long."""
    monkeypatch.setenv("PROFILE_FROM_DIAGNOSIS", "on")
    _diagnosed_on(monkeypatch, Balanced(Everything(), servers=1, slots=1), slots=2)

    assert concurrent_requests() == 1


def test_with_the_switch_off_the_cap_and_scope_stay_at_their_defaults(monkeypatch):
    monkeypatch.setenv("PROFILE_FROM_DIAGNOSIS", "off")
    _diagnosed_on(monkeypatch, Balanced(Everything(), servers=1, slots=1), slots=2)

    assert concurrent_requests() == 2
    assert session_scope() == "conversation"


def test_the_owner_s_value_on_the_settings_page_applies_with_the_switch_off(monkeypatch):
    from app.models import diagnosis_profile, diagnostics

    monkeypatch.setenv("PROFILE_FROM_DIAGNOSIS", "off")
    _diagnosed_on(monkeypatch, Balanced(Everything(), servers=2, slots=1))
    diagnosis_profile.set_override(NAME, "parallel_cap", 1)
    diagnostics.apply(model(None, name=NAME, base=ADDRESS), diagnostics.recorded(NAME))

    assert concurrent_requests() == 1
    rows = {row["id"]: row for row in steering_job.view()["profile"]["fields"]}
    assert rows["parallel_cap"]["override"] == 1 and rows["parallel_cap"]["measured"] == 2


def test_a_run_using_the_server_leaves_the_speed_not_measured(monkeypatch):
    """Company spoils a speed: with another run's call in flight on the server, nothing is kept from it."""
    from app.models import call_gate, diagnosis_profile, speed_profile

    found = server_profile.ServerProfile(slots=2, model=NAME)
    monkeypatch.setattr(server_profile, "read", lambda *args, **kwargs: found)
    server_profile.record()
    with call_gate.a_model_call(ADDRESS):
        fields = speed_profile.measure(model(Balanced(Everything(), rate=20.0, seconds=0.0), base=ADDRESS), NAME)

    assert fields == {}
    assert "a run was using" in diagnosis_profile.recorded(NAME)["speed"]["speed"]["not_measured"]
