"""An operator sees the host's health on one page: disk, database, runs waiting, model server, backup age, version.

Deep review 2026-11-18, item F5: one compose host, deploys that pause runs and a disk that filled and crashed the
database; only an operator reading the loop's output knew the state of the machine.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.server import operator_health

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def _usage(free_gib: float, total_gib: float):
    return lambda path: SimpleNamespace(free=int(free_gib * 1024**3), total=int(total_gib * 1024**3))


def test_a_data_volume_nearly_full_is_a_warning_and_a_roomy_one_is_not():
    assert operator_health.disk("/data", _usage(3, 500))["status"] == "warn"
    assert operator_health.disk("/data", _usage(40, 100))["status"] == "ok"


def test_the_newest_backup_s_age_and_a_stale_one(tmp_path):
    old, new = tmp_path / "daily" / "2026-11-16", tmp_path / "daily" / "2026-11-17"
    for folder, hours in ((old, 50), (new, 10)):
        folder.mkdir(parents=True)
        stamp = (NOW - timedelta(hours=hours)).timestamp()
        os.utime(folder, (stamp, stamp))

    fresh = operator_health.newest_backup(str(tmp_path), NOW)
    stale = operator_health.newest_backup(str(tmp_path), NOW + timedelta(hours=40))

    assert (fresh["status"], fresh["newest"], fresh["age_hours"]) == ("ok", "2026-11-17", 10.0)
    assert stale["status"] == "warn"
    assert operator_health.newest_backup("", NOW)["status"] == "unknown"


def test_runs_waiting_for_a_worker_are_listed_oldest_first_with_their_place():
    records = [
        SimpleNamespace(run_id="run-b", status="running", updated_at=(NOW - timedelta(minutes=5)).isoformat()),
        SimpleNamespace(run_id="run-a", status="running", updated_at=(NOW - timedelta(minutes=20)).isoformat()),
        SimpleNamespace(run_id="run-busy", status="running", updated_at=NOW.isoformat()),
        SimpleNamespace(run_id="run-done", status="completed", updated_at=NOW.isoformat()),
    ]

    waiting = operator_health.waiting_runs(records, lambda run: NOW if run == "run-busy" else None, NOW)

    assert [(w["run_id"], w["position"], w["minutes"]) for w in waiting] == [("run-a", 1, 20), ("run-b", 2, 5)]


def test_the_server_answers_every_part_without_calling_a_model(client, monkeypatch, tmp_path):
    from app.server import redis_client, server_health
    from app.server.models import ServerHealth

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BACKUP_DIR", "")
    monkeypatch.setattr(server_health, "read_server_health",
                        lambda busy: ServerHealth(hosted=False, answered=True, model="m", checked_at=NOW))

    def _no_redis():
        raise ConnectionError("no broker here")

    monkeypatch.setattr(redis_client, "get_async_redis_client", _no_redis)
    # The run store is shared with other tests in this process; a running record one of them left would be listed.
    from app.server.run_store import RunStore

    monkeypatch.setattr(RunStore.shared(), "list_all", lambda **_: [])

    body =client.get("/api/health/operator").json()

    assert {"status", "version", "disk", "database", "runs", "model", "backup"} <= set(body)
    assert body["model"]["status"] == "ok" and body["backup"]["status"] == "unknown"
    assert body["runs"]["waiting"] == [] and body["status"] in ("ok", "warn", "fail")
