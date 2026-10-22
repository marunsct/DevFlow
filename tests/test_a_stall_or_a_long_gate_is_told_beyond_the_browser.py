"""A run that stopped moving, or a gate left waiting, is told to a webhook and an email, once (plan OP.2)."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.server import stall_notices

NOW = datetime(2026, 10, 21, 6, 0, tzinfo=timezone.utc)


def _run(run_id, status, stage="defect_fix_2_5", updated=None):
    return SimpleNamespace(run_id=run_id, status=status, current_stage=stage,
                           updated_at=(updated or NOW).isoformat())


def test_a_quiet_running_run_and_a_long_gate_are_found_and_a_busy_one_is_not():
    activity = {"run-a": NOW - timedelta(minutes=45), "run-b": NOW - timedelta(minutes=2)}
    records = [_run("run-a", "running"), _run("run-b", "running"),
               _run("run-c", "waiting_for_review", updated=NOW - timedelta(minutes=50)), _run("run-d", "paused")]

    found = stall_notices.findings(records, NOW, activity.get)

    assert [(f["run_id"], f["kind"], f["minutes"]) for f in found] == [("run-a", "stalled", 45), ("run-c", "review waiting", 50)]


def test_each_finding_is_sent_once_to_the_webhook(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://hooks.example/notify")
    monkeypatch.delenv("NOTIFY_EMAIL", raising=False)
    posted = []
    monkeypatch.setattr(stall_notices, "send_webhook", lambda url, finding: posted.append((url, finding["run_id"])))
    finding = {"run_id": "run-a", "kind": "stalled", "stage": "s", "minutes": 45, "since": NOW.isoformat()}

    assert len(stall_notices.notify([finding])) == 1
    assert stall_notices.notify([finding]) == []
    assert posted == [("https://hooks.example/notify", "run-a")]


def test_nothing_is_sent_with_no_channel_set(monkeypatch):
    monkeypatch.delenv("NOTIFY_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("NOTIFY_EMAIL", raising=False)
    assert stall_notices.notify([{"run_id": "x", "kind": "stalled", "stage": "", "minutes": 1, "since": "t"}]) == []


def test_the_api_s_sweep_runs_it():
    from app.server import approval_timeouts

    assert "await notify_what_is_stalled(runner)" in inspect.getsource(approval_timeouts.sweep_for_ever)
