"""A run can be kept on the model it last ran on, from the API, and the pin is stored where the worker reads it.

Owner, 2026-10-30: two model servers, and a setting tied to each run - pinned, a run keeps the model it was started
with (or last ran on); unpinned, it follows the current model settings; either way it works mid-run. These tests cover
the run row, the endpoint, the start options and the status the page reads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models import model_pin
from app.server import runtime_settings

A = "http://127.0.0.1:8888/v1"
B_URL = "http://host.docker.internal:1234/v1"


@pytest.fixture(autouse=True)
def _the_settings_name_server_a(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("OPENAI_BASE_URL", A)
    monkeypatch.setenv("OPENAI_MODEL", "model-a")
    monkeypatch.setattr(runtime_settings, "overrides", lambda **_: {})
    model_pin.forget()
    yield
    model_pin.forget()


def _new_run(client, tmp_path: Path) -> str:
    brief = tmp_path / "brief.md"
    brief.write_text("A product")
    with open(brief, "rb") as handle:
        return client.post("/api/runs", files=[("files", ("brief.md", handle, "text/plain"))]).json()["run_id"]


def test_a_new_run_is_not_pinned_and_a_saved_record_cannot_change_the_pin(run_store):
    """The default is today's behaviour, and the worker's routine `save` never undoes what the API set."""
    from app.server.runner import RunRecord

    record = RunRecord(run_id="r", thread_id="t", status="running", current_stage="", stage_meaning="",
                       created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
                       document_names=[], document_paths=[])
    run_store.save(record)
    assert run_store.model_state("r") == (False, {})

    assert run_store.set_model_pin("r", True, if_unknown={"OPENAI_MODEL": "model-a"})
    run_store.save(record)  # a worker persisting its in-memory record
    assert run_store.model_state("r") == (True, {"OPENAI_MODEL": "model-a"})
    assert run_store.model_state("nobody") is None


def test_model_last_is_never_written_over_a_pin(run_store):
    """A worker recording where an unpinned run ran loses to a pin set in between: the write is conditional."""
    from app.server.runner import RunRecord

    run_store.save(RunRecord(run_id="r", thread_id="t", status="running", current_stage="", stage_meaning="",
                             created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
                             document_names=[], document_paths=[]))
    assert run_store.set_model_last("r", {"OPENAI_MODEL": "one"}) is True
    run_store.set_model_pin("r", True)
    assert run_store.set_model_last("r", {"OPENAI_MODEL": "two"}) is False
    assert run_store.model_state("r") == (True, {"OPENAI_MODEL": "one"})
    run_store.set_model_pin("r", False)
    assert run_store.model_state("r") == (False, {"OPENAI_MODEL": "one"})


def test_pinning_through_the_api_keeps_the_model_the_run_last_ran_on(client, tmp_path):
    """Pin on then off: the status shows it, and the model the run last ran on is kept (name and host:port only)."""
    run_id = _new_run(client, tmp_path)
    assert client.get(f"/api/runs/{run_id}").json()["model_pinned"] is False

    pinned = client.post(f"/api/runs/{run_id}/model-pin", json={"pinned": True})

    assert pinned.status_code == 200
    status = client.get(f"/api/runs/{run_id}").json()
    assert status["model_pinned"] is True
    assert status["model_last"] == {"model": "model-a", "endpoint": "127.0.0.1:8888"}

    client.post(f"/api/runs/{run_id}/model-pin", json={"pinned": False})
    status = client.get(f"/api/runs/{run_id}").json()
    assert status["model_pinned"] is False and status["model_last"]["model"] == "model-a"


def test_pinning_to_an_explicit_endpoint_leaves_the_global_settings_alone(client, tmp_path):
    """`base_url` and `model` pin the run to that endpoint; the settings the other runs follow do not move."""
    run_id = _new_run(client, tmp_path)
    before = runtime_settings.global_model_snapshot()

    reply = client.post(
        f"/api/runs/{run_id}/model-pin", json={"pinned": True, "base_url": B_URL, "model": "model-b"}
    )

    assert reply.status_code == 200
    assert reply.json() == {"model_pinned": True, "model_last": {"model": "model-b", "endpoint": "host.docker.internal:1234"}}
    assert client.get(f"/api/runs/{run_id}").json()["model_last"]["model"] == "model-b"
    assert runtime_settings.global_model_snapshot() == before
    assert runtime_settings.global_model_snapshot()["OPENAI_BASE_URL"] == A
    # And the run, seen from inside, is on B while the global view is still A.
    with model_pin.as_the_run(run_id):
        assert runtime_settings.effective_environment()["OPENAI_BASE_URL"] == B_URL
        assert runtime_settings.effective_environment(ignore_run=True)["OPENAI_BASE_URL"] == A


@pytest.mark.parametrize("payload", [
    {"pinned": True, "base_url": "ftp://host/v1"},
    {"pinned": True, "base_url": "http://user:secret@host:1234/v1"},
    {"pinned": True, "base_url": "not a url"},
    {"pinned": True, "base_url": ""},
    {"pinned": True, "model": "   "},
    {"pinned": False, "base_url": B_URL},
    {"pinned": True, "api_key": "secret"},
])
def test_a_pin_to_a_bad_endpoint_or_with_a_credential_is_refused(client, tmp_path, payload):
    """The address is http(s) without credentials, the model name is not empty, and no key is accepted at all."""
    run_id = _new_run(client, tmp_path)
    refused = client.post(f"/api/runs/{run_id}/model-pin", json=payload)
    assert refused.status_code == 422
    assert client.get(f"/api/runs/{run_id}").json()["model_pinned"] is False


def test_pinning_a_run_that_does_not_exist_is_a_404(client):
    assert client.post("/api/runs/nope/model-pin", json={"pinned": True}).status_code == 404


def test_a_run_started_pinned_to_an_endpoint_is_on_it_from_the_start(client, tmp_path):
    """`pin_model` with `pin_base_url` and `pin_model_name` fixes the run's first snapshot; the settings stay as they are."""
    run_id = _new_run(client, tmp_path)

    started = client.post(f"/api/runs/{run_id}/start", json={
        "pin_model": True, "pin_base_url": B_URL, "pin_model_name": "model-b", "workspace_label": "pin-test"})

    assert started.status_code == 202
    status = client.get(f"/api/runs/{run_id}").json()
    assert status["model_pinned"] is True and status["model_last"]["model"] == "model-b"
    assert runtime_settings.global_model_snapshot()["OPENAI_MODEL"] == "model-a"


def test_a_run_started_without_a_pin_records_the_model_it_starts_on(client, tmp_path):
    """Unpinned, `model_last` starts as what the settings name now (and then follows them)."""
    run_id = _new_run(client, tmp_path)
    assert client.post(f"/api/runs/{run_id}/start", json={"workspace_label": "pin-test-2"}).status_code == 202
    status = client.get(f"/api/runs/{run_id}").json()
    assert status["model_pinned"] is False and status["model_last"]["model"] == "model-a"


def test_a_start_with_a_bad_pin_address_is_refused_before_anything_is_prepared(client, tmp_path):
    run_id = _new_run(client, tmp_path)
    refused = client.post(f"/api/runs/{run_id}/start", json={"pin_model": True, "pin_base_url": "http://u:p@h/v1"})
    assert refused.status_code == 422
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "created"
    refused = client.post(f"/api/runs/{run_id}/start", json={"pin_base_url": B_URL})
    assert refused.status_code == 422


def test_no_snapshot_holds_a_credential(client, tmp_path):
    """What is stored for the run, and what the status shows, never contains a key."""
    run_id = _new_run(client, tmp_path)
    client.post(f"/api/runs/{run_id}/model-pin", json={"pinned": True, "base_url": B_URL, "model": "model-b"})
    from app.server.run_store import RunStore

    stored = RunStore.shared().model_state(run_id)[1]
    assert set(stored) <= set(runtime_settings.MODEL_KEYS)
    assert not any("KEY" in name and name != "OPENAI_BASE_URL" for name in stored)
    assert "secret" not in json.dumps(stored).lower()
