"""A test run that has printed its closing summary and then does not exit is ended, not timed out.

Measured live: a product's test setup opened a database engine whose thread
kept pytest alive after it printed "7 errors in 0.26s". Every run a fixer
started waited out its timeout - 300 s, then 60 s, then 60 s - and came back
as a timeout, with the result it had in fact printed buried in it.
"""
from __future__ import annotations

import sys
import time

from app.tools import sandbox

LINGERS = (
    "import threading, time\n"
    "print('{summary}', flush=True)\n"
    "threading.Thread(target=lambda: time.sleep(120)).start()\n"
)


def _run(tmp_path, summary, *, watched=True, timeout=60):
    script = tmp_path / "lingers.py"
    script.write_text(LINGERS.format(summary=summary))
    started = time.monotonic()
    result = sandbox._run_and_watch_the_tree(
        [sys.executable, str(script)], cwd=str(tmp_path), env={"PATH": "/usr/bin:/bin"},
        timeout=timeout, ends_at_its_summary=watched,
    )
    return result, time.monotonic() - started


def test_a_run_that_lingers_after_a_passing_summary_ends_and_passes(tmp_path):
    result, took = _run(tmp_path, "3 passed in 0.12s")

    assert took < 20
    assert result.returncode == 0 and getattr(result, "lingered", False)
    assert "3 passed in 0.12s" in result.stdout


def test_a_run_that_lingers_after_errors_ends_and_fails(tmp_path):
    result, took = _run(tmp_path, "2 warnings, 7 errors in 0.26s")

    assert took < 20
    assert result.returncode == 1


def test_a_command_that_is_not_a_test_run_is_left_alone(tmp_path):
    import subprocess

    try:
        _run(tmp_path, "3 passed in 0.12s", watched=False, timeout=8)
    except subprocess.TimeoutExpired:
        return
    raise AssertionError("an unwatched command must run to its timeout")


def test_the_summary_shapes():
    assert sandbox._the_run_has_summed_up("collected 3 items\n\n=== 3 passed in 1.20s ===\n")
    assert sandbox._the_run_has_summed_up("2 warnings, 7 errors in 0.26s")
    assert sandbox._the_run_has_summed_up("=== no tests ran in 0.01s ===")
    assert not sandbox._the_run_has_summed_up("3 passed in 0.12s\nnow starting the server")
    assert sandbox._what_the_summary_says("1 failed, 2 passed in 0.3s") == 1
    assert sandbox._what_the_summary_says("2 passed in 0.3s") == 0


def test_the_stage_is_told_why(tmp_path):
    import inspect

    source = inspect.getsource(sandbox)
    assert "ends_at_its_summary=_runs_tests(argv)" in source
    assert "close or dispose of it when the tests end" in source
