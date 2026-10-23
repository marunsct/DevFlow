"""The settings page showed nothing of a finished diagnosis, and an image was sent to a server that holds no vision part.

The diagnosis (worker) kept its findings under the model file the server holds;
the API behind the settings page never read the server and looked under the
configured name, so every row said "not yet" / "not measured" - and what the
owner set there went to a file no run read. And the capability probe sent a
picture to a server whose `/props` said `vision: false`: a 400 at best, a hung
server at worst.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.models import capabilities, model_guidance, registry, server_profile, steering_job

CONFIGURED = "Org/Some-Model-GGUF"
SERVED = "Some-Model-GGUF"


@pytest.fixture(autouse=True)
def _data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MODEL_READS_IMAGES", raising=False)
    server_profile.forget()
    monkeypatch.setattr("app.models._runtime_settings",
                        lambda: SimpleNamespace(model_name=CONFIGURED, llm_provider="local",
                                                openai_base_url="http://x/v1", openai_api_key=""))
    yield
    server_profile.forget()


def _serves(monkeypatch, *, model=SERVED, vision=False):
    props = {"model_path": model, "total_slots": 3, "modalities": {"vision": vision}}
    monkeypatch.setattr(server_profile, "read", lambda *a, **k: server_profile.from_props(props))


def test_the_server_s_vision_part_is_read_from_its_props():
    assert server_profile.from_props({"model_path": "m", "modalities": {"vision": False}}).reads_images is False
    assert server_profile.from_props({"model_path": "m", "modalities": {"vision": True}}).reads_images is True
    assert server_profile.from_props({"model_path": "m"}).reads_images is None


def test_the_page_names_the_model_as_the_worker_does(monkeypatch):
    _serves(monkeypatch)
    registry.merge_into_fitness(SERVED, {"deep_diagnosis": {"reply_ceiling": 40000}})
    assert steering_job.page_model() == SERVED
    assert steering_job.view()["model"] == SERVED
    assert steering_job.view()["settings"]["reply_ceiling"] == 40000


def test_what_was_kept_under_the_configured_name_moves_to_the_served_one(monkeypatch):
    _serves(monkeypatch)
    registry.merge_into_fitness(CONFIGURED, {"capabilities_owner": {"reasons": True, "reads_images": False}})
    registry.merge_into_fitness(SERVED, {"capabilities_owner": {"reasons": False}, "edit": 1.0})

    steering_job.page_model()

    kept = json.loads((registry.fitness_dir() / f"{registry._slug(SERVED)}.json").read_text())
    assert kept["capabilities_owner"] == {"reasons": False, "reads_images": False}  # the served file's value wins
    assert kept["edit"] == 1.0 and kept["model"] == SERVED
    assert not (registry.fitness_dir() / f"{registry._slug(CONFIGURED)}.json").exists()


def test_a_server_that_says_nothing_leaves_the_configured_name(monkeypatch):
    monkeypatch.setattr(server_profile, "read", lambda *a, **k: None)
    assert steering_job.page_model() == CONFIGURED
    assert model_guidance.served_as(CONFIGURED) == CONFIGURED


def test_the_server_is_read_again_when_the_read_is_old_so_a_swapped_model_is_named(monkeypatch):
    _serves(monkeypatch, model="First-GGUF")
    assert server_profile.recent(clock=lambda: 0.0).model == "First-GGUF"
    _serves(monkeypatch, model="Second-GGUF")
    assert server_profile.recent(clock=lambda: 1.0).model == "First-GGUF"  # fresh enough: no new read
    assert server_profile.recent(clock=lambda: server_profile._READ_AT + 100).model == "Second-GGUF"


class _Counting:
    def __init__(self):
        self.images = 0
        self.sent = []

    def create(self, **payload):
        self.sent.append(payload)
        if isinstance(payload["messages"][-1]["content"], list):
            self.images += 1
        return {"choices": [{"finish_reason": "stop", "message": {"content": "Tokyo."}}]}


def _model(server):
    return SimpleNamespace(model_name=CONFIGURED, root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)))


def test_no_image_is_sent_to_a_server_that_holds_no_vision_part(monkeypatch):
    _serves(monkeypatch, vision=False)
    server_profile.record()
    monkeypatch.setattr(capabilities, "look_up", lambda names: {})
    monkeypatch.setattr("app.models.diagnostics.the_model_answers", lambda model: True)
    server = _Counting()

    found = capabilities.fill(_model(server), SERVED, CONFIGURED)

    assert server.images == 0
    assert found["reads_images"]["value"] is False and found["reads_images"]["source"] == "server"


def test_an_image_is_still_sent_when_the_server_says_nothing_of_vision(monkeypatch):
    monkeypatch.setattr(server_profile, "read", lambda *a, **k: server_profile.from_props({"model_path": SERVED}))
    server_profile.record()
    monkeypatch.setattr(capabilities, "look_up", lambda names: {})
    monkeypatch.setattr("app.models.diagnostics.the_model_answers", lambda model: True)
    server = _Counting()

    capabilities.fill(_model(server), SERVED, CONFIGURED)

    assert server.images == 1
