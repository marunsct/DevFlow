"""A cgroup CPU quota does not change what a tool thinks it can parallelise.

Measured on run-cbd22a34, twice:

    worker container CPU limit     2   (cgroup cpu.max = 200000 100000)
    host cores                    20
    nproc / os.cpus() inside      20   <- the quota is invisible here

Vitest forked one worker per *reported* CPU - twenty - each permitted
`SANDBOX_MEMORY_LIMIT` of heap by RLIMIT_DATA. The tree reached the container's
memory limit exactly at 4 GiB, and again after it was raised to 8 GiB:

    memory.peak = 4294975488   oom_kill 27   WorkerLostError signal 9
    memory.peak = 8589934592   oom_kill 2    WorkerLostError signal 9

Raising the ceiling could never fix that; the multiplier was wrong. Per-process
rlimits multiply by the number of processes, so bounding one process is not
bounding the command.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import _concurrency_environment, _usable_cpus


def test_a_cpu_quota_is_read_rather_than_the_core_count(tmp_path, monkeypatch):
    cgroup = tmp_path / "cpu.max"
    cgroup.write_text("200000 100000\n")

    import builtins

    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if str(path) == "/sys/fs/cgroup/cpu.max":
            return real_open(cgroup, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    assert _usable_cpus() == 2, "a 2-CPU quota must read as 2, not as the host's cores"


def test_an_unlimited_quota_falls_back_to_affinity(tmp_path, monkeypatch):
    cgroup = tmp_path / "cpu.max"
    cgroup.write_text("max 100000\n")

    import builtins

    real_open = builtins.open
    monkeypatch.setattr(
        builtins, "open",
        lambda p, *a, **k: real_open(cgroup, *a, **k) if str(p) == "/sys/fs/cgroup/cpu.max" else real_open(p, *a, **k),
    )

    assert _usable_cpus() >= 1


def test_the_heap_budget_is_divided_across_the_pool():
    """`SANDBOX_MEMORY_LIMIT` is what one process may hold; this is what the
    whole pool may hold together."""
    environment = _concurrency_environment()

    assert environment["NODE_OPTIONS"].startswith("--max-old-space-size=")
    megabytes = int(environment["NODE_OPTIONS"].split("=")[1])
    assert megabytes >= 256, "a heap too small to run anything is not a bound, it is a break"


def test_the_pool_size_is_capped_for_the_runners_that_read_it():
    environment = _concurrency_environment()

    assert environment["VITEST_MAX_THREADS"] == str(_usable_cpus())
    assert environment["VITEST_MAX_FORKS"] == str(_usable_cpus())
    assert int(environment["UV_THREADPOOL_SIZE"]) <= 8


def test_the_child_environment_carries_it(tmp_path):
    from app.tools.sandbox import _child_environment

    environment = _child_environment(str(tmp_path), None)

    assert "NODE_OPTIONS" in environment
    assert "VITEST_MAX_THREADS" in environment


def test_a_caller_can_still_override(tmp_path):
    """Applied before `extra_env`, so a deliberate override wins."""
    from app.tools.sandbox import _child_environment

    environment = _child_environment(str(tmp_path), {"NODE_OPTIONS": "--max-old-space-size=64"})

    assert environment["NODE_OPTIONS"] == "--max-old-space-size=64"
