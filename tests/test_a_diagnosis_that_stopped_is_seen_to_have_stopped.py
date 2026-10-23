"""A diagnosis that stops without finishing is shown as stopped, and can be started again.

The settings page stayed on "diagnosing" through a closed model server and a
restart of every container: the status file said running, nothing ever said
otherwise, and the action refused to start while it did. And a model server
that went away mid-diagnosis would have had its failed questions kept as the
model's answers.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.models import steering_job


@pytest.fixture(autouse=True)
def _data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def test_a_running_status_whose_heartbeat_stopped_is_failed(monkeypatch):
    steering_job.set_status("running", "asking the stage-shaped questions")
    assert steering_job.status()["status"] == "running"

    later = steering_job._now() + steering_job.STALE_SECONDS + 1
    monkeypatch.setattr(steering_job, "_now", lambda: later)
    assert steering_job.status() == {"status": "failed", "message": steering_job.STOPPED}


def test_a_status_from_before_the_heartbeat_is_failed_too():
    path = steering_job._status_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"status": "running", "message": "queued", "at": "2026-10-23T10:00:00+00:00"}))
    assert steering_job.status()["status"] == "failed"


def test_the_heartbeat_keeps_a_running_job_running(monkeypatch):
    steering_job.set_status("running", "deep diagnosis")
    later = steering_job._now() + steering_job.STALE_SECONDS + 1
    monkeypatch.setattr(steering_job, "_now", lambda: later)
    steering_job._beat()
    assert steering_job.status() == {"status": "running", "message": "deep diagnosis"}


def test_a_server_gone_mid_diagnosis_keeps_nothing_of_that_part(monkeypatch):
    from app.models import deep_diagnosis, diagnostics, reply_salvage, server_profile
    import app.models as models

    answers = iter([True, False])  # answers at the start, gone after the tool questions
    monkeypatch.setattr(diagnostics, "the_model_answers", lambda model: next(answers))
    monkeypatch.setattr(diagnostics, "diagnose", lambda model, name: SimpleNamespace(model=name))
    kept = []
    monkeypatch.setattr(diagnostics, "keep", lambda d: kept.append(d))
    monkeypatch.setattr(server_profile, "record", lambda: None)
    monkeypatch.setattr(models, "build_default_chat_model", lambda: SimpleNamespace(model_name="m"))
    monkeypatch.setattr(reply_salvage, "served_name", lambda model: "m")

    steering_job.run()

    assert kept == []
    assert steering_job.status()["status"] == "failed" and "stopped answering" in steering_job.status()["message"]


def test_the_action_starts_again_once_a_stopped_job_is_seen(client, monkeypatch) -> None:
    from app.server import settings, tasks

    steering_job.set_status("running", "queued")
    monkeypatch.setattr(steering_job, "_now", lambda: 10**12)
    monkeypatch.setattr(settings, "_a_run_is_live", lambda: False)
    queued = []
    monkeypatch.setattr(tasks.diagnose_the_model, "delay", lambda: queued.append(True))

    assert client.post("/api/settings/model/steering/diagnose").status_code == 202 and queued == [True]
