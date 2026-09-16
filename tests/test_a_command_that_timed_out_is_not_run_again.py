"""A command that timed out is refused rather than run a second time.

Run 0c5aabdb's `specialist_backend_1` ran `node simple-to-do-list-app/index.js`
twice and spent four minutes of wall clock on a server the sandbox has nobody
to connect to - which is exactly what the timeout message says, delivered
after the second 120 seconds had already been paid.

Every other repeated failure costs a model call. This one costs a model call
and the whole timeout, so it is the one worth refusing before it runs rather
than noting after.

Timeouts need their own check because they record no exit code - the process
never exited - so `failed_this_way_before`'s `returncode not in (0, None)`
test excludes all of them.
"""

import json

import pytest

from app.tools.sandbox import (
    SandboxExecutor,
    failed_this_way_before,
    timed_out_this_way_before,
)

SERVER = ["node", "app/index.js"]


def _ledger(root, entries):
    from app.tools.sandbox import _ledger_path

    path = _ledger_path(str(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")


def _timeout_entry(command=SERVER, working_directory=None):
    return {
        "at": "2026-09-16T20:00:00+00:00",
        "role": "backend_specialist",
        "command": command,
        "working_directory": working_directory,
        "category": "default",
        "returncode": None,
        "error": "Command timed out after 120 seconds. A command that does not finish...",
    }


def test_a_previous_timeout_is_counted(tmp_path):
    _ledger(tmp_path, [_timeout_entry()])

    assert timed_out_this_way_before(str(tmp_path), SERVER) == 1


def test_the_ordinary_failure_check_misses_it(tmp_path):
    """Which is why this needs its own: a timeout records no exit code."""
    _ledger(tmp_path, [_timeout_entry()])

    assert failed_this_way_before(str(tmp_path), SERVER) == 0


def test_a_different_command_is_not_counted(tmp_path):
    _ledger(tmp_path, [_timeout_entry()])

    assert timed_out_this_way_before(str(tmp_path), ["node", "--test"]) == 0


def test_a_command_that_merely_failed_is_not_counted(tmp_path):
    _ledger(
        tmp_path,
        [{"command": SERVER, "working_directory": None, "returncode": 1, "error": None}],
    )

    assert timed_out_this_way_before(str(tmp_path), SERVER) == 0


def test_no_ledger_at_all_is_not_an_error(tmp_path):
    assert timed_out_this_way_before(str(tmp_path), SERVER) == 0


def test_the_second_run_is_refused_without_executing(tmp_path, monkeypatch):
    _ledger(tmp_path, [_timeout_entry()])
    ran = {"called": False}

    def _fake_run(cls, *args, **kwargs):
        ran["called"] = True
        return {"returncode": "0", "stdout": "", "stderr": ""}

    monkeypatch.setattr(SandboxExecutor, "_run", classmethod(_fake_run))

    outcome = SandboxExecutor.execute(SERVER, str(tmp_path), "backend_specialist")

    assert ran["called"] is False
    assert "already timed out" in outcome["error"]
    assert "would time out again" in outcome["error"]


def test_the_refusal_keeps_the_advice_the_timeout_gives(tmp_path, monkeypatch):
    """The alternative matters more than the prohibition."""
    _ledger(tmp_path, [_timeout_entry()])
    monkeypatch.setattr(
        SandboxExecutor, "_run", classmethod(lambda cls, *a, **k: {"returncode": "0"})
    )

    outcome = SandboxExecutor.execute(SERVER, str(tmp_path), "backend_specialist")

    assert "Nothing here will connect to a server" in outcome["error"]


def test_a_first_run_is_not_refused(tmp_path, monkeypatch):
    ran = {"called": False}

    def _fake_run(cls, *args, **kwargs):
        ran["called"] = True
        return {"returncode": "0", "stdout": "", "stderr": ""}

    monkeypatch.setattr(SandboxExecutor, "_run", classmethod(_fake_run))

    SandboxExecutor.execute(SERVER, str(tmp_path), "backend_specialist")

    assert ran["called"] is True
