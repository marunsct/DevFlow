"""A run can be given a name, so it can be told from the others in the list of runs.

Owner, 2026-10-31: with several runs of the same brief the list showed only ids and stages; the person could not tell
which run was which. A name is set when the run starts (`RUN_NAME` in the loop scripts) or from the run's page, is
shown in the page header and in the list, and is stored where a worker saving its record cannot undo it.
"""
from __future__ import annotations

from app.server.runner import RunRecord


def _record(run_id: str) -> RunRecord:
    return RunRecord(run_id=run_id, thread_id="t-" + run_id, status="running", current_stage="", stage_meaning="",
                     created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
                     document_names=[], document_paths=[])


def test_a_name_is_stored_read_for_a_page_of_runs_and_cleared(run_store):
    for run_id in ("a", "b"):
        run_store.save(_record(run_id))
    assert run_store.set_run_name("a", "tasks-api on 8888")
    assert run_store.run_names(["a", "b", "nobody"]) == {"a": "tasks-api on 8888"}
    assert run_store.set_run_name("a", None)
    assert run_store.run_names(["a"]) == {}
    assert not run_store.set_run_name("nobody", "x")
    assert run_store.run_names([]) == {}


def test_a_worker_saving_its_record_does_not_undo_a_rename(run_store):
    record = _record("a")
    run_store.save(record)
    run_store.set_run_name("a", "kept")
    run_store.save(record)  # the worker persisting its in-memory record
    assert run_store.run_names(["a"]) == {"a": "kept"}


def _new_run(client, tmp_path) -> str:
    brief = tmp_path / "brief.md"
    brief.write_text("A product")
    with open(brief, "rb") as handle:
        return client.post("/api/runs", files=[("files", ("brief.md", handle, "text/plain"))]).json()["run_id"]


def test_the_name_is_set_from_the_api_and_shown_by_the_list_and_the_status(client, tmp_path):
    run_id = _new_run(client, tmp_path)
    assert {r["run_id"]: r for r in client.get("/api/runs").json()["runs"]}[run_id]["run_name"] is None

    reply = client.post(f"/api/runs/{run_id}/name", json={"name": "  fix-loop   ON,  8888  "})

    assert reply.status_code == 200 and reply.json()["run_name"] == "fix-loop ON, 8888"
    assert {r["run_id"]: r for r in client.get("/api/runs").json()["runs"]}[run_id]["run_name"] == "fix-loop ON, 8888"
    assert client.get(f"/api/runs/{run_id}").json()["run_name"] == "fix-loop ON, 8888"

    assert client.post(f"/api/runs/{run_id}/name", json={"name": "   "}).json()["run_name"] is None
    assert client.get(f"/api/runs/{run_id}").json().get("run_name") is None


def test_a_name_that_is_too_long_or_for_no_run_is_refused(client, tmp_path):
    run_id = _new_run(client, tmp_path)
    assert client.post(f"/api/runs/{run_id}/name", json={"name": "x" * 81}).status_code == 422
    assert client.post("/api/runs/nobody/name", json={"name": "x"}).status_code == 404


def test_the_loop_scripts_can_name_a_run_at_the_start():
    from pathlib import Path

    script = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "loop.sh").read_text()
    assert 'RUN_NAME:+, \\"name\\": \\"$RUN_NAME\\"' in script
