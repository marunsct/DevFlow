"""The notices that stop a re-run must reach both tools that run commands.

`SandboxExecutor.execute` attaches them - "this exact command has already
failed 3 times", "already passed and nothing has been written since", the
doubled-working-directory correction. `run_approved_validation` built a fresh
reply dict and dropped every one, so they reached `run_terminal_command` and
never reached `run_validation`, which is the tool the specialist prompt names
for running tests.

Measured on run-84e05d4b's `specialist_testing_1`: 53 model calls, `node --test`
run six times through this path and three through the other. Only the three
could be told anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import RepositoryToolError, run_approved_validation


@pytest.fixture()
def executed(monkeypatch):
    """Stand in for the sandbox, returning whatever a test wants it to."""
    import app.tools.sandbox as sandbox

    outcome: dict = {}

    def fake_execute(**kwargs):
        return dict(outcome)

    monkeypatch.setattr(sandbox.SandboxExecutor, "execute", staticmethod(fake_execute))
    return outcome


def test_a_repeat_notice_reaches_the_caller(tmp_path: Path, executed) -> None:
    executed.update(
        {
            "stdout": "not ok 1",
            "stderr": "",
            "returncode": "1",
            "note": "This exact command has already failed 3 time(s) in this run.",
        }
    )

    result = run_approved_validation(tmp_path, ["node", "--test"])

    assert "already failed 3 time(s)" in result["note"]
    assert result["returncode"] == 1


def test_a_run_with_nothing_to_say_carries_no_note(tmp_path: Path, executed) -> None:
    executed.update({"stdout": "ok", "stderr": "", "returncode": "0"})

    result = run_approved_validation(tmp_path, ["node", "--test"])

    assert "note" not in result
    assert result["returncode"] == 0


def test_a_refused_command_is_returned_as_data(tmp_path: Path, executed) -> None:
    """A refusal carries an `error` and no exit code; `int()` on that raised."""
    executed.update({"error": "'sh' is not permitted for role 'testing_specialist'."})

    result = run_approved_validation(tmp_path, ["sh", "build.sh"])

    assert result["returncode"] == -1
    assert "not permitted" in result["stderr"]


def test_an_unparsable_exit_code_does_not_raise(tmp_path: Path, executed) -> None:
    executed.update({"stdout": "", "stderr": "", "returncode": "killed"})

    result = run_approved_validation(tmp_path, ["node", "--test"])

    assert isinstance(result["returncode"], int)


def test_a_string_command_is_still_refused(tmp_path: Path) -> None:
    with pytest.raises(RepositoryToolError, match="must be a list"):
        run_approved_validation(tmp_path, "node --test")
