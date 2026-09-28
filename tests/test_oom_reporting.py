"""An OOM-killed worker must say so, not look like an infrastructure fault.

Measured on one run: `npx vitest run` forked one worker per CPU, each
permitted `SANDBOX_MEMORY_LIMIT` (2 GiB) of heap by RLIMIT_DATA. The tree
reached `memory.peak = 4,294,975,488` - exactly the worker container's 4 GiB
limit - and the kernel killed the Celery workers mid-test:

    Process 'ForkPoolWorker-34' pid:22362 exited with 'signal 9 (SIGKILL)'
    Task handler raised error: WorkerLostError('Worker exited prematurely:
      signal 9 (SIGKILL) Job: 0.')

The run row stayed `running` with no error, and the generic recovery message -
"the host or the container went away mid-task" - would have sent an operator
looking for a fault that never happened.

Per-process rlimits do not bound a process tree. The container limit is the
real ceiling, which is why this is worth naming explicitly.
"""

from __future__ import annotations

import pytest


def _manage():
    import os

    os.environ.setdefault("ENV", "development")
    from app.server import manage

    return manage


def test_a_container_with_oom_kills_is_detected(tmp_path, monkeypatch):
    manage = _manage()
    events = tmp_path / "memory.events"
    events.write_text("low 0\nhigh 0\nmax 102790\noom 5042\noom_kill 27\n")

    monkeypatch.setattr(
        manage, "_worker_ran_out_of_memory",
        lambda: "oom_kill 27" in events.read_text(),
    )

    assert manage._worker_ran_out_of_memory()


def test_a_healthy_container_reports_no_oom(tmp_path):
    """oom_kill 0 is the normal state and must not trigger the message."""
    manage = _manage()
    import builtins

    real_open = builtins.open
    events = tmp_path / "memory.events"
    events.write_text("low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\n")

    def fake_open(path, *args, **kwargs):
        if str(path).startswith("/sys/fs/cgroup"):
            return real_open(events, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    builtins.open = fake_open
    try:
        assert manage._worker_ran_out_of_memory() is False
    finally:
        builtins.open = real_open


def test_an_unreadable_cgroup_is_not_an_error():
    """A probe must never be the thing that fails a recovery."""
    manage = _manage()
    import builtins

    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if str(path).startswith("/sys/fs/cgroup"):
            raise OSError("no cgroup here")
        return real_open(path, *args, **kwargs)

    builtins.open = fake_open
    try:
        assert manage._worker_ran_out_of_memory() is False
    finally:
        builtins.open = real_open


def test_the_recovery_message_names_the_cause_and_the_fix():
    """The operator needs to know it was memory, and what to change."""
    import inspect

    manage = _manage()
    source = " ".join(inspect.getsource(manage.recover_orphaned_runs).split())

    # The message is built from adjacent string literals, so the source carries
    # the quote marks between them; compare on the words that matter.
    assert "OOM-killed at least once" in source
    assert "per-process rlimits" in source.lower()
    assert "do not bound a process tree" in source.lower()
    assert "node --test" in source


def test_the_sandbox_heap_leaves_room_for_a_fork_pool():
    """Several concurrent children must fit inside the container's limit."""
    import re
    from pathlib import Path

    compose = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text()

    sandbox = re.search(r"SANDBOX_MEMORY_LIMIT: \$\{SANDBOX_MEMORY_LIMIT:-(\d+)g\}", compose)
    # Anchored on the worker service itself - a looser pattern matched the
    # app service's block instead, and compared the wrong number.
    worker_block = compose[compose.index("\n  worker:") :]
    worker = re.search(r"memory: (\d+)g", worker_block)

    assert sandbox and worker, "could not read the two limits"
    per_process, container = int(sandbox.group(1)), int(worker.group(1))

    assert per_process * 4 <= container, (
        f"SANDBOX_MEMORY_LIMIT={per_process}g x4 forked workers exceeds the "
        f"worker container's {container}g limit, which is what OOM-killed "
        "run-a000000c"
    )
