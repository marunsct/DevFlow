"""The run after one that used the whole time limit gets a short limit.

Measured on one run: a suite with a loop that never ends was run three times in
one sprint - 300 seconds each, a quarter of an hour in which nothing else
happened. Files had changed between the runs, so the guard that refuses an
identical repeat did not apply, and each run waited the full limit again.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tools.sandbox import (
    SHORTEST_RETRY_TIMEOUT_SECONDS,
    _ledger_path,
    after_a_run_that_never_finished,
)

TEST = ["node", "--test", "tests/tasks.test.js"]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "the-app-run-abc"
    root.mkdir()
    return root


def _ran(root: Path, *entries: dict) -> None:
    path = _ledger_path(str(root))
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")


def _timed_out(seconds: float, argv=TEST, where="the-app") -> dict:
    return {
        "command": argv, "working_directory": where, "returncode": 124,
        "error": f"Command timed out after {int(seconds)} seconds.", "duration_seconds": seconds,
    }


def _finished(code: int, argv=TEST, where="the-app") -> dict:
    return {"command": argv, "working_directory": where, "returncode": code, "duration_seconds": 1.2}


def test_a_command_never_run_gets_the_whole_limit(workspace) -> None:
    assert after_a_run_that_never_finished(workspace, TEST, "the-app", 300) == 300


def test_the_run_after_a_full_timeout_is_short(workspace) -> None:
    _ran(workspace, _timed_out(300.2))

    assert after_a_run_that_never_finished(workspace, TEST, "the-app", 300) == SHORTEST_RETRY_TIMEOUT_SECONDS


def test_the_run_after_a_short_timeout_gets_the_whole_limit_again(workspace) -> None:
    """A command that is merely slow is never held to the short limit twice."""
    _ran(workspace, _timed_out(300.2), _timed_out(60.1))

    assert after_a_run_that_never_finished(workspace, TEST, "the-app", 300) == 300


def test_a_run_that_finished_since_restores_the_limit(workspace) -> None:
    _ran(workspace, _timed_out(300.2), _finished(1))

    assert after_a_run_that_never_finished(workspace, TEST, "the-app", 300) == 300


def test_another_command_or_another_directory_is_not_affected(workspace) -> None:
    _ran(workspace, _timed_out(300.2))

    assert after_a_run_that_never_finished(workspace, ["npm", "test"], "the-app", 300) == 300
    assert after_a_run_that_never_finished(workspace, TEST, "elsewhere", 300) == 300


def test_a_long_limit_is_cut_to_a_share_of_itself(workspace) -> None:
    _ran(workspace, _timed_out(900.0))

    assert after_a_run_that_never_finished(workspace, TEST, "the-app", 900) == 180
