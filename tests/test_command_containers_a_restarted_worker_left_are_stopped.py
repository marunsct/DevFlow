"""Command containers a restarted worker left running are stopped when a worker starts (found on the host).

Measured: eight `dotnet test` command containers from one family's runs ran for three days, 2.4 GB between them - a
deploy restarted the worker mid-command, which killed only the client that waited for each.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.tools import sandbox

NOW = datetime(2026, 11, 24, 2, 0, tzinfo=timezone.utc)


def _docker(started: dict[str, str]):
    calls = []

    def run(argv, **_kwargs):
        calls.append(argv)
        if argv[1] == "ps":
            return SimpleNamespace(stdout="\n".join(started), returncode=0)
        if argv[1] == "inspect":
            return SimpleNamespace(stdout="\n".join(f"/{n} {started[n]}" for n in argv[4:]), returncode=0)
        return SimpleNamespace(stdout="", returncode=0)
    return run, calls


def test_a_container_running_past_every_timeout_is_stopped_and_a_running_command_is_not(monkeypatch):
    monkeypatch.setattr(sandbox, "_docker_binary", lambda: "docker")
    run, calls = _docker({"sandbox-old": "2026-11-21T09:00:00.123456789Z", "sandbox-new": "2026-11-24T01:55:00.5Z"})

    stopped = sandbox.end_the_commands_nobody_waits_for(run=run, now=NOW)

    assert stopped == ["sandbox-old"]
    assert ["docker", "kill", "sandbox-old"] in calls and ["docker", "kill", "sandbox-new"] not in calls


def test_no_command_container_means_nothing_is_done(monkeypatch):
    monkeypatch.setattr(sandbox, "_docker_binary", lambda: "docker")
    run, calls = _docker({})

    assert sandbox.end_the_commands_nobody_waits_for(run=run, now=NOW) == []
    assert len(calls) == 1


def test_a_worker_starting_runs_the_sweep():
    from app.server import tasks

    assert callable(tasks._stop_the_commands_a_previous_worker_left)  # noqa: SLF001
