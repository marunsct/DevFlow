"""A run's time paused is kept apart from its time, however it was paused (owner, 2026-11-03).

The run's page showed the time since the run was created; a run paused for an hour while the model's server rested
read an hour slower than it ran. The database keeps the pause clock itself, so every writer is counted.
"""
from __future__ import annotations

from dataclasses import replace

from app.server.runner import RunRecord


def _record(run_id: str, status: str) -> RunRecord:
    return RunRecord(run_id=run_id, thread_id="t-" + run_id, status=status, current_stage="", stage_meaning="",
                     created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
                     document_names=[], document_paths=[])


def _pushed_back(run_store, run_id: str, seconds: int) -> None:
    """As if the pause began `seconds` ago."""
    with run_store.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE runs SET paused_since = paused_since - make_interval(secs => %s) WHERE run_id = %s",
                        (seconds, run_id))
        conn.commit()


def test_each_pause_is_added_once_it_ends_and_the_one_going_on_is_counted_now(run_store):
    record = _record("a", "running")
    run_store.save(record)
    assert run_store.paused_seconds(["a"]) == {"a": 0.0}

    run_store.save(replace(record, status="paused"))
    _pushed_back(run_store, "a", 120)
    assert 119 <= run_store.paused_seconds(["a"])["a"] <= 130, "the pause going on now counts"

    run_store.save(replace(record, status="running"))
    after_one = run_store.paused_seconds(["a"])["a"]
    assert 119 <= after_one <= 130

    run_store.save(replace(record, status="running"))  # a worker saving again adds nothing
    assert abs(run_store.paused_seconds(["a"])["a"] - after_one) < 2

    run_store.save(replace(record, status="paused"))
    _pushed_back(run_store, "a", 60)
    run_store.save(replace(record, status="completed"))
    assert 179 <= run_store.paused_seconds(["a"])["a"] <= 195


def test_the_status_says_how_long_the_run_was_paused(run_store, client, tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("A product")
    with open(brief, "rb") as handle:
        run_id = client.post("/api/runs", files=[("files", ("brief.md", handle, "text/plain"))]).json()["run_id"]
    assert client.get(f"/api/runs/{run_id}").json().get("paused_seconds", 0) == 0
    with run_store.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE runs SET paused_seconds = 90 WHERE run_id = %s", (run_id,))
        conn.commit()
    assert client.get(f"/api/runs/{run_id}").json()["paused_seconds"] == 90
