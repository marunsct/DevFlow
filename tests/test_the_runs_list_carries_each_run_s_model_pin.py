"""The runs list says which runs are kept on their model, so a switch can sit on every row.

Owner, 2026-10-31: the per-run model pin existed only in a run's own page header, as a plain checkbox; the person
looking at the list of runs saw no switch "with each run". The list returns each run's pin and the model it last ran
on (name and host:port only), read with one statement for the whole page.
"""
from __future__ import annotations

from app.server.runner import RunRecord


def _record(run_id: str) -> RunRecord:
    return RunRecord(run_id=run_id, thread_id="t-" + run_id, status="running", current_stage="", stage_meaning="",
                     created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
                     document_names=[], document_paths=[])


def test_one_statement_reads_the_pin_of_every_run_asked_for(run_store):
    for name in ("a", "b", "c"):
        run_store.save(_record(name))
    run_store.set_model_pin("a", True, if_unknown={"OPENAI_MODEL": "m-a", "OPENAI_BASE_URL": "http://h:8888/v1"})

    states = run_store.model_states(["a", "b", "nobody"])

    assert states["a"] == (True, {"OPENAI_MODEL": "m-a", "OPENAI_BASE_URL": "http://h:8888/v1"})
    assert states["b"] == (False, {})
    assert "nobody" not in states and "c" not in states
    assert run_store.model_states([]) == {}


def test_a_failed_read_leaves_the_list_working(run_store, monkeypatch):
    def broken():
        raise RuntimeError("no database")

    monkeypatch.setattr(run_store, "get_connection", broken)
    assert run_store.model_states(["a"]) == {}


def test_the_list_response_names_the_pin_and_the_model(client, tmp_path):
    """`GET /api/runs` carries `model_pinned` and `model_last` for each run, with no key in either."""
    brief = tmp_path / "brief.md"
    brief.write_text("A product")
    with open(brief, "rb") as handle:
        run_id = client.post("/api/runs", files=[("files", ("brief.md", handle, "text/plain"))]).json()["run_id"]

    before = {r["run_id"]: r for r in client.get("/api/runs").json()["runs"]}[run_id]
    assert before["model_pinned"] is False

    reply = client.post(f"/api/runs/{run_id}/model-pin",
                        json={"pinned": True, "base_url": "http://host.docker.internal:1234/v1", "model": "qwen-b"})
    assert reply.status_code == 200

    after = {r["run_id"]: r for r in client.get("/api/runs").json()["runs"]}[run_id]
    assert after["model_pinned"] is True
    assert after["model_last"] == {"model": "qwen-b", "endpoint": "host.docker.internal:1234"}
    assert "key" not in str(after).lower()
