"""A run started with the frontier model checks first that the model is configured and answering.

Owner, 2026-10-19: with "use the frontier model" ticked and no frontier model
set - or one whose key was refused - a run started anyway, and its
specification and reviews ran on the local model or failed at the first
judgement stage. The check reads the settings and asks the endpoint for its
model listing: a read, never a model call.
"""

from __future__ import annotations

import pytest

from app.models import frontier_check

LOCAL = {"LLM_PROVIDER": "local", "OPENAI_BASE_URL": "http://model:8080/v1"}


@pytest.fixture(autouse=True)
def _fresh():
    frontier_check.forget()
    yield
    frontier_check.forget()


def test_none_configured_says_where_to_set_one():
    found = frontier_check.check_frontier(LOCAL, reader=lambda request: pytest.fail("nothing to ask"))
    assert (found["configured"], found["active"]) == (False, False)
    assert "Settings" in found["problem"]


def test_a_hosted_model_without_its_key_is_not_configured():
    found = frontier_check.check_frontier({**LOCAL, "JUDGEMENT_MODEL": "claude-x", "JUDGEMENT_PROVIDER": "anthropic"},
                                          reader=lambda request: pytest.fail("no key to ask with"))
    assert found["configured"] is False and "no key" in found["problem"]


def test_a_refused_key_is_configured_but_not_active():
    environment = {**LOCAL, "JUDGEMENT_MODEL": "claude-x", "JUDGEMENT_PROVIDER": "anthropic", "JUDGEMENT_API_KEY": "k"}
    asked = []

    found = frontier_check.check_frontier(environment, reader=lambda request: asked.append(request.full_url) or "refused its key (HTTP 401)")

    assert asked == ["https://api.anthropic.com/v1/models"]
    assert (found["configured"], found["active"]) == (True, False) and "refused its key" in found["problem"]


def test_an_answering_model_is_ready_and_is_asked_at_most_once_a_minute():
    environment = {**LOCAL, "JUDGEMENT_MODEL": "big", "JUDGEMENT_BASE_URL": "http://judge:9000/v1"}
    asked = []
    now = [100.0]

    def reader(request):
        asked.append(request.full_url)
        return None

    found = frontier_check.check_frontier(environment, reader=reader, clock=lambda: now[0])
    frontier_check.check_frontier(environment, reader=reader, clock=lambda: now[0] + 30)

    assert found == {"configured": True, "active": True, "model": "big", "provider": "local", "problem": None}
    assert len(asked) == 1 and asked[0].endswith("/v1/models")


def test_the_start_route_refuses_a_frontier_run_the_check_fails(client, tmp_path, monkeypatch):
    monkeypatch.setattr(frontier_check, "check_frontier", lambda *a, **k: {"problem": "No frontier model is configured."})
    brief = tmp_path / "brief.md"
    brief.write_text("A product")
    with open(brief, "rb") as handle:
        run_id = client.post("/api/runs", files=[("files", ("brief.md", handle, "text/plain"))]).json()["run_id"]

    refused = client.post(f"/api/runs/{run_id}/start", json={"use_frontier_model": True})

    assert refused.status_code == 409 and refused.json()["detail"] == "No frontier model is configured."
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "created"


def test_the_status_route_answers_the_check(client, monkeypatch):
    monkeypatch.setattr(frontier_check, "check_frontier", lambda *a, **k: {"configured": True, "active": True, "model": "m", "provider": "p", "problem": None})
    assert client.get("/api/settings/frontier/status").json()["active"] is True
