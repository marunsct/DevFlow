"""The diagnosis asks its independent requests side by side, as many at once as the server really serves (owner, 2026-11-27).

The owner: "if the model supports more parallel request run the diagnosis parallely". The tool diagnosis asked its
forty-odd requests one after another, and the deep diagnosis each guide's few tries as a batch of its own; none named
a session, so a balancer placed them all by the same opening bytes. Never more at once than the server's slots less
what live runs have in flight there; each request its own session; results as a serial run's; one failed request
never loses the others; a hosted model held to a small number at once and to the diagnosis's cost ceiling.
"""
from __future__ import annotations

import contextlib

from dataclasses import asdict

import pytest

from app.models import call_gate, deep_diagnosis, diagnostics, server_profile
from tests.diagnosis_fakes import Everything, Overlapping, StageChecks, ToolChecks, model

ADDRESS = "http://model-server:2001/v1"
NAME = "a-model.gguf"


@pytest.fixture(autouse=True)
def _a_fresh_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path / "gate"))
    monkeypatch.setenv("OPENAI_BASE_URL", ADDRESS)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("MODEL_GUIDANCE", "on")
    monkeypatch.delenv("HARNESS_MAX_PARALLEL", raising=False)
    server_profile.forget()
    yield
    server_profile.forget()


def _slots(monkeypatch, slots: int | None) -> None:
    """The model server says it serves `slots` requests at once (None: it says nothing of itself)."""
    found = server_profile.ServerProfile(slots=slots, model=NAME) if slots else None
    monkeypatch.setattr(server_profile, "read", lambda *args, **kwargs: found)
    server_profile.forget()
    server_profile.record()


def _without_times(diagnosis) -> dict:
    record = asdict(diagnosis)
    for key in ("measured_at", "seconds", "fingerprint"):
        record.pop(key, None)
    return record


def test_the_tool_diagnosis_asks_as_many_at_once_as_the_server_has_slots(monkeypatch):
    _slots(monkeypatch, 3)
    server = Overlapping(ToolChecks())

    diagnostics.diagnose(model(server, base=ADDRESS), NAME)

    assert server.most == 3


@pytest.mark.parametrize("slots", [None, 1])
def test_a_server_that_serves_one_at_a_time_or_says_nothing_is_asked_one_at_a_time(monkeypatch, slots):
    _slots(monkeypatch, slots)
    server = Overlapping(StageChecks())

    deep_diagnosis.diagnose(model(server, base=ADDRESS), NAME)

    assert server.most == 1


def test_the_calls_live_runs_have_in_flight_take_their_slots(monkeypatch):
    """Three slots, two of them serving another run's calls: the deep diagnosis asks one at a time."""
    from app.models.model_guidance import deep_if_new

    _slots(monkeypatch, 3)
    server = Overlapping(Everything())
    with contextlib.ExitStack() as calls:
        for _ in range(2):
            calls.enter_context(call_gate.a_model_call(ADDRESS))
        deep_if_new(model(server, base=ADDRESS))

    assert deep_diagnosis.recorded(NAME) is not None
    assert server.most == 1


def test_each_request_names_a_session_of_its_own(monkeypatch):
    """A balancer keeps a session on one server: a diagnosis's requests each get their own, so they spread."""
    _slots(monkeypatch, 4)
    server = Overlapping(StageChecks(), hold=0.0)

    deep_diagnosis.diagnose(model(server, base=ADDRESS), NAME)

    assert None not in server.sessions
    assert len(set(server.sessions)) == len(server.sessions)


def test_side_by_side_answers_read_as_a_serial_run(monkeypatch):
    def plan_in_schema(system, n):
        return n == 1

    def as_server(slots):
        _slots(monkeypatch, slots)
        stage = StageChecks({"a plan answered in its schema": plan_in_schema})
        return (_without_times(diagnostics.diagnose(model(Overlapping(ToolChecks(), hold=0.0), base=ADDRESS), NAME)),
                _without_times(deep_diagnosis.diagnose(model(Overlapping(stage, hold=0.0), base=ADDRESS), NAME)))

    assert as_server(4) == as_server(1)


def test_a_job_that_fails_leaves_its_error_in_its_place_and_the_others_answer():
    from app.models.diagnosis_pool import side_by_side

    def broken():
        raise ValueError("a reply that could not be read")

    answers = side_by_side([lambda: 1, broken, lambda: 3], at_once=3)

    assert answers[0] == 1 and answers[2] == 3
    assert isinstance(answers[1], ValueError)


HOSTED = "https://api.example.com/v1"


class _Priced:
    """A hosted model answering every check right; each reply reports 100,000 prompt tokens."""

    def __init__(self):
        self.stage = Overlapping(StageChecks(), hold=0.01)

    def create(self, **payload):
        reply = self.stage.create(**payload)
        return {**reply, "usage": {"prompt_tokens": 100_000, "completion_tokens": 100}}


def test_a_hosted_model_is_asked_two_at_once_and_held_to_its_cost_ceiling(monkeypatch):
    """At the dearest rate an unpriced model is counted at, a reply of 100,000 prompt tokens costs 1 USD: the
    ceiling of 2 USD sends a few requests and leaves the rest not measured, never failed."""
    monkeypatch.setenv("DIAGNOSIS_MAX_COST_USD", "2")
    _slots(monkeypatch, None)
    server = _Priced()

    diagnosis = deep_diagnosis.diagnose(model(server, name="a-hosted-model", base=HOSTED), "a-hosted-model")

    assert server.stage.most <= 2
    sent = len(server.stage.sessions)
    assert 2 <= sent <= 4
    assert sum(r.unmeasured for r in diagnosis.baseline) == 36 - sent
    assert all(r.passed == r.tries for r in diagnosis.baseline)


def test_the_settings_page_is_told_how_many_requests_have_been_answered(monkeypatch):
    from app import models
    from app.models import capabilities, steering_job

    _slots(monkeypatch, 2)
    seen: list[str] = []

    class Reading(Everything):
        def create(self, **payload):
            seen.append(steering_job.status()["message"])
            return super().create(**payload)

    monkeypatch.setattr(models, "build_default_chat_model", lambda *a, **k: model(Reading(), base=ADDRESS))
    # The model card lookups reach the internet; what the page is told is the point here.
    monkeypatch.setattr(capabilities, "fill", lambda *a, **k: {})

    steering_job.run()

    assert steering_job.status()["status"] == "idle", steering_job.status()
    assert any("answered, up to 2 at once" in message for message in seen)
