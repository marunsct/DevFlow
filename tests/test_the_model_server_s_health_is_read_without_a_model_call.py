"""The page learns the model server's state and the run's ceilings without a model call (plan BG.1, BG.5).

The worker reads the server's `/props` and keeps what it says in its own
process, where the API cannot see it; the run page had no way to say what the
server holds, how many requests it serves at once, or that one run waits on
another. And the run payload carried the spend but not the ceilings it is held
to, so no page could draw how close a run is to being paused.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models import server_profile
from app.models.server_profile import ServerProfile, from_props
from app.server import server_health

LOCAL = SimpleNamespace(llm_provider="local", openai_base_url="http://model:8080/v1", openai_api_key="", model_name="configured")


@pytest.fixture(autouse=True)
def _fresh():
    server_health.forget()
    yield
    server_health.forget()


def test_the_server_s_own_account_with_the_runs_on_it():
    asked = []

    def reader(base_url, api_key):
        asked.append(base_url)
        return ServerProfile(slots=1, slot_context=126_464, quantisation="Q4_K_M", model="Qwen3.6-35B-Q4_K_M.gguf")

    health = server_health.read_server_health(["run-a"], reader=reader, settings=LOCAL)

    assert asked == ["http://model:8080/v1"]
    assert (health.answered, health.slots, health.slot_context) == (True, 1, 126_464)
    assert health.model == "Qwen3.6-35B-Q4_K_M.gguf" and health.busy_runs == ["run-a"]


def test_it_is_read_at_most_once_a_minute_and_the_runs_are_always_current():
    calls = []
    reader = lambda base_url, api_key: calls.append(1) or ServerProfile(slots=2)  # noqa: E731
    now = [1000.0]

    server_health.read_server_health(["run-a"], clock=lambda: now[0], reader=reader, settings=LOCAL)
    now[0] += server_health.CACHE_SECONDS - 1
    again = server_health.read_server_health(["run-b"], clock=lambda: now[0], reader=reader, settings=LOCAL)
    assert len(calls) == 1 and again.busy_runs == ["run-b"]

    now[0] += 2
    server_health.read_server_health([], clock=lambda: now[0], reader=reader, settings=LOCAL)
    assert len(calls) == 2


def test_a_server_that_does_not_answer_and_a_hosted_api_say_so():
    silent = server_health.read_server_health([], reader=lambda *_: None, settings=LOCAL)
    assert (silent.hosted, silent.answered, silent.model) == (False, False, "configured")

    server_health.forget()
    hosted = server_health.read_server_health(
        [], reader=lambda *_: pytest.fail("a hosted API has no status to read"),
        settings=SimpleNamespace(llm_provider="anthropic", model_name="claude"),
    )
    assert (hosted.hosted, hosted.model) == (True, "claude")


def test_the_model_is_named_by_its_file():
    props = {"model_path": "/models/unsloth/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf", "total_slots": 2}
    assert from_props(props).model == "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"


def test_the_route_answers_without_a_model_call(client, monkeypatch):
    monkeypatch.setattr(server_profile, "read", lambda base_url, api_key="": ServerProfile(slots=1, model="m.gguf"))

    body = client.get("/api/health/server").json()

    assert body["slots"] == 1 and body["model"] == "m.gguf" and isinstance(body["busy_runs"], list)


def test_the_run_payload_carries_its_ceilings(client, tmp_path: Path, monkeypatch):
    brief = tmp_path / "brief.md"
    brief.write_text("A product")
    with open(brief, "rb") as handle:
        run_id = client.post("/api/runs", files=[("files", ("brief.md", handle, "text/plain"))]).json()["run_id"]

    monkeypatch.setenv("MAX_RUN_TOKENS", "5000000")
    monkeypatch.delenv("MAX_RUN_COST_USD", raising=False)
    body = client.get(f"/api/runs/{run_id}").json()

    assert body["max_run_tokens"] == 5_000_000
    assert body["max_run_cost_usd"] is None
