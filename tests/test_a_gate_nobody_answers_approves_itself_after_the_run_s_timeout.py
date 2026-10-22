"""A gate that asks a person approves itself once the run's timeout has passed."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.server import approval_timeouts
from app.server.models import StartRunRequest
from app.server.run_store import _INSERT_SQL, _SELECT_ONE_SQL, _MIGRATIONS

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def _run(run_id, status, minutes, waited):
    return SimpleNamespace(run_id=run_id, status=status, approval_timeout_minutes=minutes,
                           updated_at=(NOW - timedelta(minutes=waited)).isoformat())


RUNS = [
    _run("a", "waiting_for_approval", 30, 31),
    _run("b", "waiting_for_review", 30, 45),
    _run("c", "waiting_for_review", 30, 10),
    _run("d", "waiting_for_review", None, 999),
    _run("e", "running", 30, 999),
]


def test_only_a_gate_past_its_run_s_timeout_is_due():
    assert approval_timeouts.due(RUNS, NOW) == [("a", "approval", 30), ("b", "review", 30)]


def test_due_gates_are_approved_and_one_another_process_took_is_skipped():
    calls = []

    class _Runner:
        run_store = SimpleNamespace(list_all=lambda limit, offset: RUNS)

        async def submit_approval(self, run_id, decision):
            raise RuntimeError("Run a is not waiting for approval.")

        async def submit_review(self, run_id, decision):
            calls.append((run_id, decision))

    approved = asyncio.run(approval_timeouts.approve_what_is_due(_Runner(), NOW))

    assert approved == ["b"]
    assert "nobody answered within 30 minute(s)" in str(calls[0][1])


def test_the_timeout_is_chosen_per_run_and_kept():
    assert StartRunRequest(approval_timeout_minutes=30).approval_timeout_minutes == 30
    assert StartRunRequest().approval_timeout_minutes is None
    assert "approval_timeout_minutes" in _INSERT_SQL and "approval_timeout_minutes" in _SELECT_ONE_SQL
    assert any("approval_timeout_minutes" in statement for statement in _MIGRATIONS)
