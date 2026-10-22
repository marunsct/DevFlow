"""A command is stopped when its processes together use more than it may have.

Measured on one run: `npm test` started a runner with a worker per CPU, each
inside its own per-process limit. Together they took what the container had,
the kernel killed the Celery worker instead of any of them, then the two that
replaced it, and the container restarted with the run still marked running.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from app.tools import sandbox
from app.tools.sandbox import _TreeOverBudget, _run_and_watch_the_tree, _tree_memory_bytes

pytestmark = pytest.mark.skipif(not os.path.isdir("/proc/self"), reason="needs /proc")

#: Two children of 60 MB each, and a parent that waits for them.
A_TREE = (
    "import os, time\n"
    "for _ in range(2):\n"
    "    if os.fork() == 0:\n"
    "        held = bytearray(60 * 1024 * 1024)\n"
    "        for i in range(0, len(held), 4096): held[i] = 1\n"
    "        time.sleep(30)\n"
    "        os._exit(0)\n"
    "time.sleep(30)\n"
)


def _run(code: str, timeout: int = 20):
    return _run_and_watch_the_tree(
        [sys.executable, "-c", code], cwd=os.getcwd(), env=dict(os.environ), timeout=timeout
    )


def test_a_tree_over_its_budget_is_stopped_with_a_reason(monkeypatch) -> None:
    monkeypatch.setattr(sandbox, "_tree_budget_bytes", lambda: 80 * 1024**2)
    started = time.monotonic()

    with pytest.raises(_TreeOverBudget) as caught:
        _run(A_TREE)

    assert time.monotonic() - started < 15, "stopped by the watch, not by the timeout"
    assert caught.value.used_mb > caught.value.budget_mb == 80


def test_the_same_tree_within_its_budget_runs(monkeypatch) -> None:
    monkeypatch.setattr(sandbox, "_tree_budget_bytes", lambda: 4 * 1024**3)

    result = _run("print('ok')")

    assert result.returncode == 0 and result.stdout.strip() == "ok"


def test_a_timeout_takes_the_children_with_it(monkeypatch, tmp_path) -> None:
    """`subprocess.run` killed the direct child and left its workers running."""
    monkeypatch.setattr(sandbox, "_tree_budget_bytes", lambda: 4 * 1024**3)
    marker = tmp_path / "child.pid"
    code = (
        "import os, time\n"
        "if os.fork() == 0:\n"
        f"    open({str(marker)!r}, 'w').write(str(os.getpid()))\n"
        "    time.sleep(60)\n"
        "    os._exit(0)\n"
        "time.sleep(60)\n"
    )

    with pytest.raises(subprocess.TimeoutExpired):
        _run(code, timeout=2)

    child = int(marker.read_text())
    time.sleep(0.5)
    alive = os.path.exists(f"/proc/{child}") and "Z" not in open(f"/proc/{child}/stat").read().rsplit(")", 1)[-1].split()[0]
    assert not alive


def test_the_measure_counts_every_process_in_the_group() -> None:
    process = subprocess.Popen([sys.executable, "-c", A_TREE], start_new_session=True)
    try:
        time.sleep(2.5)
        assert _tree_memory_bytes(process.pid) > 100 * 1024**2
    finally:
        os.killpg(process.pid, 9)
        process.wait()


def test_the_refusal_reaches_the_stage_as_a_failed_command(monkeypatch, tmp_path) -> None:
    def over(*args, **kwargs):
        raise _TreeOverBudget(3 * 1024**3, 2 * 1024**3, "out", "err")

    monkeypatch.setattr(sandbox, "_run_and_watch_the_tree", over)

    outcome = sandbox.SandboxExecutor._execute_here(
        ["node", "--version"], str(tmp_path), "testing_specialist", "test", 30, None
    )

    assert outcome["returncode"] == "137"
    assert "its processes together were using 3072 MB" in outcome["error"]
    assert "one test file at a time" in outcome["error"]
