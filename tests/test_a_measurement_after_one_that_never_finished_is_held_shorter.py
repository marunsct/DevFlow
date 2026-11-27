"""The harness's own test run after one ended at its limit is held to a limit its finished runs earned (LF.1643).

Measured on a service run: the harness ran the unit tests four times, on four versions of the product, each to the
300-second limit, after the same `npm test` had finished in about a second five times - twenty minutes in which
neither the model nor anything else was busy. The agents' rule for the same thing (`after_a_run_that_never_finished`)
never applied to the harness's own measurements.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.tools import sandbox
from app.tools.sandbox import SHORTEST_RETRY_TIMEOUT_SECONDS, SandboxExecutor, _ledger_path

TEST = ["npm", "test"]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "workspace-run-abc"
    (root / "notes-api").mkdir(parents=True)
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
    monkeypatch.setattr(sandbox, "_docker_binary", lambda: "/usr/bin/docker")
    from app.tools import resources

    monkeypatch.setattr(resources, "enough_headroom", lambda *args, **kwargs: (True, ""))
    return root


def _ran(root: Path, *entries: dict) -> None:
    path = _ledger_path(str(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")


def _finished(seconds: float, by: str = "agent") -> dict:
    return {"command": TEST, "working_directory": "notes-api", "returncode": 1, "duration_seconds": seconds, "by": by}


def _ended_at_the_limit(seconds: float = 300.1, by: str = "harness") -> dict:
    return {"command": TEST, "working_directory": "notes-api", "returncode": None, "duration_seconds": seconds,
            "error": f"Command timed out after {int(seconds)} seconds.", "by": by}


def _the_limit_the_harness_s_run_is_given(root: Path, monkeypatch) -> int:
    given: list[int] = []

    def docker(argv, *args, **kwargs):
        if argv[1] == "run":
            given.append(kwargs["timeout"])
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(sandbox.subprocess, "run", docker)
    SandboxExecutor.execute(TEST, str(root), "testing_specialist", "test", working_directory="notes-api",
                            for_the_harness=True)
    assert len(given) == 1
    return given[0]


def test_after_a_run_ended_at_the_limit_the_next_measurement_is_held_shorter(workspace, monkeypatch):
    _ran(workspace, _finished(0.8), _finished(1.05), _ended_at_the_limit(by="agent"))

    assert _the_limit_the_harness_s_run_is_given(workspace, monkeypatch) == SHORTEST_RETRY_TIMEOUT_SECONDS


def test_it_stays_shorter_while_the_runs_keep_ending_at_the_limit(workspace, monkeypatch):
    _ran(workspace, _finished(1.0), _ended_at_the_limit(), _ended_at_the_limit(60.1))

    assert _the_limit_the_harness_s_run_is_given(workspace, monkeypatch) == SHORTEST_RETRY_TIMEOUT_SECONDS


def test_a_suite_that_takes_long_when_it_finishes_keeps_three_times_that(workspace, monkeypatch):
    _ran(workspace, _finished(70.0), _ended_at_the_limit())

    assert _the_limit_the_harness_s_run_is_given(workspace, monkeypatch) == 211


@pytest.mark.parametrize("history", [
    [],
    [_ended_at_the_limit()],
    [_ended_at_the_limit(), _finished(1.0)],
], ids=["never run", "never finished", "finished since"])
def test_otherwise_it_gets_the_whole_limit(workspace, monkeypatch, history):
    if history:
        _ran(workspace, *history)

    assert _the_limit_the_harness_s_run_is_given(workspace, monkeypatch) == sandbox.timeout_for("test", str(workspace))
