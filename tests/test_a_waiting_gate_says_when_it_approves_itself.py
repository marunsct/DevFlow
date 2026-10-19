"""A waiting gate says when it approves itself - or that it waits for the person.

A gate approved itself with nobody told, and gates with no timeout sat parked
12-13 h with nothing to say they would wait for ever.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.server.models import RunStatusResponse
from app.server.runs import _when_the_gate_approves_itself


def _record(status, minutes, updated="2026-10-18T03:00:00+00:00"):
    return SimpleNamespace(status=status, approval_timeout_minutes=minutes, updated_at=updated)


def test_a_waiting_gate_with_a_timeout_has_its_deadline():
    assert _when_the_gate_approves_itself(_record("waiting_for_review", 30)) == datetime(2026, 10, 18, 3, 30, tzinfo=timezone.utc)


def test_no_timeout_or_nothing_waiting_has_none():
    assert _when_the_gate_approves_itself(_record("waiting_for_approval", None)) is None
    assert _when_the_gate_approves_itself(_record("running", 30)) is None


def test_the_run_payload_carries_it():
    assert {"gate_deadline", "approval_timeout_minutes"} <= set(RunStatusResponse.model_fields)


def test_the_runs_list_carries_it_so_the_inbox_can_say_it(client, monkeypatch):
    """The header's inbox lists every waiting run from one call to the list."""
    from app.server.run_store import RunStore
    from app.server.runner import RunRecord

    waiting = RunRecord(
        run_id="run-a", thread_id="t", document_names=[], document_paths=[],
        status="waiting_for_approval", updated_at="2026-10-18T03:00:00+00:00", approval_timeout_minutes=30,
    )
    monkeypatch.setattr(RunStore, "list_all", lambda self, **kwargs: [waiting])
    monkeypatch.setattr(RunStore, "count", lambda self, *args, **kwargs: 1)

    (run,) = client.get("/api/runs").json()["runs"]

    assert run["gate_deadline"].startswith("2026-10-18T03:30:00")
