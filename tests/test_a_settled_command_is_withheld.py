"""A command that has already passed three times is withheld, not run again.

`succeeded_this_way_before` has appended a note since the leak it documents was
first measured. This run showed the note is not enough on its own.

`defect_fix_1_0`, live on 2026-09-21, ran::

    wc -l task-manager/index.html task-manager/style.css task-manager/app.js

eleven times, with exactly one write before the first of them. The note fired
correctly on calls four through eleven and counted up as it went - "already
passed 1 time(s)", "2 time(s)", ... "8 time(s)" - and the stage ran the command
again after each one. Eight notices, eight ignored.

So it escalates the way `aeb1e3a` escalated a repeated *read*: notice first,
withhold when the notice is not heeded. A write re-arms the command, which is
what keeps a genuine edit-test loop working.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import SUCCESSES_BEFORE_WITHHOLDING


COMMAND = ["wc", "-l", "app.js"]


@pytest.fixture
def executor(tmp_path, monkeypatch):
    """`SandboxExecutor.execute` with the container run (`_run`) stood in for: every run passes, and is counted."""
    from app.tools.sandbox import SandboxExecutor

    (tmp_path / "app.js").write_text("x\n")
    ran = []

    def passes(cls, command, *args, **kwargs):
        ran.append(list(command))
        return {"returncode": "0", "stdout": "1 app.js\n", "stderr": ""}

    monkeypatch.setattr(SandboxExecutor, "_run", classmethod(passes))
    return lambda: SandboxExecutor.execute(COMMAND, str(tmp_path), "backend_specialist"), ran


def test_a_command_passed_three_times_with_nothing_written_is_not_run_again(executor):
    execute, ran = executor
    for _ in range(SUCCESSES_BEFORE_WITHHOLDING):
        execute()

    withheld = execute()

    assert len(ran) == 3, "the fourth is withheld, not run"
    said = withheld["error"]
    assert "already passed 3 time(s)" in said and "nothing has been written since" in said, "how many times and why"
    assert "change a file first" in said, "the way out"
    assert "withheld rather than repeated" in said, "that the notice was ignored"


def test_a_write_where_it_runs_lets_it_run_again(executor, tmp_path):
    """A write must re-arm the command, or an edit-test loop would stall."""
    import os
    import time

    execute, ran = executor
    for _ in range(SUCCESSES_BEFORE_WITHHOLDING):
        execute()
    edited = tmp_path / "app.js"
    edited.write_text("y\n")
    later = time.time() + 60
    os.utime(edited, (later, later))

    execute()

    assert len(ran) == 4


def test_a_withheld_command_still_reaches_the_ledger(executor, tmp_path):
    """A stage that was stopped is different from one that never tried: the ledger is what the repeat checks and the
    audit script read."""
    from app.tools.sandbox import read_execution_ledger

    execute, _ = executor
    for _ in range(SUCCESSES_BEFORE_WITHHOLDING + 1):
        execute()

    last = read_execution_ledger(str(tmp_path))[-1]
    assert last["command"] == COMMAND and "Not running this again" in str(last.get("error"))
