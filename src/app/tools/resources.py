"""What this container may actually use, read at the moment of use.

Every limit in the sandbox used to be a static number from the environment:
`SANDBOX_MEMORY_LIMIT` is what one process may hold, `SANDBOX_CPU_LIMIT` how
many CPUs it may use. Nothing asked what was left. That is how one run
died twice: the worker was already holding the conversation, a test runner
forked a worker per CPU, the tree reached the container's limit, and the kernel
killed the celery workers mid-run. The run was not failed, it was orphaned -
there is no error to report when the process holding the error is gone.

A refused command is a tool result the model can read and work around. An OOM
kill is a dead run and a post-mortem. This module exists to convert the second
into the first, by asking three questions before a command starts:

- how much memory does this cgroup allow, and how much is already used
- how many CPUs may this cgroup actually use (not how many exist)
- has anything here been OOM-killed already

Nothing here raises. Resource introspection that fails a run would be worse
than the problem it is diagnosing, so every reader falls back and the state
carries `None` for what it could not determine.

Concurrency is handled by measurement rather than by arithmetic. The worker
runs `--concurrency=2`, so two runs share one cgroup, and `memory.current` is
their combined usage. A budget computed from it is therefore already the shared
budget: when one run is heavy the other is told there is little room, without
either of them knowing the other exists. Dividing a static limit by a worker
count would have needed every caller to agree on that count, and would have
been wrong the moment the setting changed.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_CGROUP_V2 = "/sys/fs/cgroup"
_CGROUP_V1_MEMORY = "/sys/fs/cgroup/memory"

#: Kept back for the worker itself. The process that launches a command keeps
#: growing while the command runs - it is streaming model output into the same
#: container - so handing a command everything currently free is how both die.
_RESERVE_FRACTION = 0.15
_RESERVE_FLOOR_BYTES = 512 * 1024**2

#: Below this there is no point starting: a Node or Python runtime alone needs
#: more, so the command would fail on allocation rather than on its own merits.
_VIABLE_FLOOR_BYTES = 256 * 1024**2


def _read_int(path: str) -> int | None:
    """One integer from a sysfs file, or None if it cannot be read."""
    try:
        with open(path, encoding="utf-8") as handle:
            value = handle.read().strip()
    except (OSError, ValueError):
        return None
    if value in ("max", "-1", ""):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _read_field(path: str, field: str) -> int | None:
    """One `name value` line from a sysfs file such as `memory.events`."""
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                name, _, value = line.partition(" ")
                if name == field:
                    return int(value.strip())
    except (OSError, ValueError):
        return None
    return None


def _total_system_memory() -> int | None:
    """`MemTotal` from /proc/meminfo, for a host with no cgroup limit at all."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _available_system_memory() -> int | None:
    """`MemAvailable` - what can be allocated without swapping."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def usable_cpus() -> int:
    """How many CPUs this container may use, not how many the host has.

    A cgroup CPU quota does not change what `nproc` or `os.cpus()` report.
    Measured on one run: the worker is limited to 2 CPUs, the host has 20,
    every tool inside the container saw 20, and a test runner forked twenty
    workers. Raising the memory limit could never have fixed that - the
    multiplier was wrong, not the ceiling.
    """
    for path in (f"{_CGROUP_V2}/cpu.max", "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"):
        try:
            with open(path, encoding="utf-8") as handle:
                raw = handle.read().split()
            if path.endswith("cpu.max"):
                quota, period = raw[0], raw[1]
            else:
                quota = raw[0]
                period = str(_read_int("/sys/fs/cgroup/cpu/cpu.cfs_period_us") or 100000)
            if quota not in ("max", "-1"):
                return max(1, int(int(quota) / int(period)))
        except (OSError, ValueError, IndexError):
            continue
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


@dataclass(frozen=True)
class ResourceState:
    """What the container allows and what it is using, right now.

    `None` means "could not be determined here", which is the normal answer on
    a developer machine with no cgroup limits. Callers must treat it as "do not
    restrict" rather than as zero - refusing to run because a limit could not be
    read would make the sandbox unusable outside a container.
    """

    memory_limit: int | None
    memory_in_use: int | None
    memory_peak: int | None
    oom_kills: int
    cpus: int
    pids_in_use: int | None

    @property
    def headroom(self) -> int | None:
        """Memory that could still be allocated inside this cgroup."""
        if self.memory_limit is None or self.memory_in_use is None:
            return None
        return max(0, self.memory_limit - self.memory_in_use)

    @property
    def was_oom_killed(self) -> bool:
        """Whether the kernel has already killed something in this cgroup.

        The signal a post-mortem needs: a worker that vanished mid-run leaves
        no exception behind, only this counter.
        """
        return self.oom_kills > 0

    def describe(self) -> str:
        """One line for a log or an error message, in units people read."""

        def mb(value: int | None) -> str:
            return "unknown" if value is None else f"{value / 1024**2:,.0f} MiB"

        return (
            f"limit {mb(self.memory_limit)}, in use {mb(self.memory_in_use)}, "
            f"headroom {mb(self.headroom)}, peak {mb(self.memory_peak)}, "
            f"{self.cpus} CPU(s), oom_kills {self.oom_kills}"
        )


def read_resource_state() -> ResourceState:
    """Read the cgroup now. Never raises; unknown fields come back as None."""
    limit = _read_int(f"{_CGROUP_V2}/memory.max")
    in_use = _read_int(f"{_CGROUP_V2}/memory.current")
    peak = _read_int(f"{_CGROUP_V2}/memory.peak")
    oom = _read_field(f"{_CGROUP_V2}/memory.events", "oom_kill")

    if limit is None and in_use is None:  # cgroup v1
        limit = _read_int(f"{_CGROUP_V1_MEMORY}/memory.limit_in_bytes")
        in_use = _read_int(f"{_CGROUP_V1_MEMORY}/memory.usage_in_bytes")
        peak = _read_int(f"{_CGROUP_V1_MEMORY}/memory.max_usage_in_bytes")

    # A v1 "unlimited" limit is a sentinel close to 2^63, not a real ceiling.
    if limit is not None and limit >= 2**62:
        limit = None

    if limit is None:
        # No cgroup ceiling: the host's own memory is the real one, and what is
        # free there is the honest measure of headroom.
        total = _total_system_memory()
        available = _available_system_memory()
        if total is not None and available is not None:
            limit, in_use = total, total - available

    return ResourceState(
        memory_limit=limit,
        memory_in_use=in_use,
        memory_peak=peak,
        oom_kills=oom or 0,
        cpus=usable_cpus(),
        pids_in_use=_read_int(f"{_CGROUP_V2}/pids.current"),
    )


def memory_budget(ceiling: int, state: ResourceState | None = None) -> int:
    """What one command may have, given what is left and what `ceiling` allows.

    `ceiling` is the configured per-command limit - the most a command may have
    when the container is idle. This returns the smaller of that and what is
    actually free, minus a reserve for the worker's own growth.

    The static number alone is what failed: `SANDBOX_MEMORY_LIMIT` said 1 GiB
    per process, and it was true of each process. The tree was twenty of them.
    """
    state = state or read_resource_state()
    headroom = state.headroom
    if headroom is None:
        return ceiling

    reserve = max(
        _RESERVE_FLOOR_BYTES,
        int((state.memory_limit or 0) * _RESERVE_FRACTION),
    )
    return max(0, min(ceiling, headroom - reserve))


def enough_headroom(ceiling: int, state: ResourceState | None = None) -> tuple[bool, str]:
    """Whether a command should start at all, and why not when it should not.

    The refusal is the product here. A command told "there is 180 MiB free and
    a runtime needs more than that" can report a blocker, and the run continues
    with an explanation. A command that starts anyway takes the worker with it
    and the run ends with no error at all, because the process that would have
    written one is gone.
    """
    state = state or read_resource_state()
    budget = memory_budget(ceiling, state)
    if state.headroom is None or budget >= _VIABLE_FLOOR_BYTES:
        return True, ""

    return False, (
        "Not enough memory is free in this container to run that safely "
        f"({state.describe()}). Starting it would risk the kernel killing this "
        "run rather than failing the command.\n"
        "What helps, in order: wait for the current work to finish and retry; "
        "run a smaller piece of it (one test file rather than the suite); or "
        "raise the worker's memory limit in docker-compose.yml if the work "
        "genuinely needs more."
    )


def concurrency_environment(ceiling: int, state: ResourceState | None = None) -> dict[str, str]:
    """Environment telling child runtimes the real CPU count and heap budget.

    Per-process rlimits multiply by the number of processes, so bounding one
    process is not bounding the command. These are the levers the common
    runtimes actually read, and they are set from the live budget rather than
    the configured ceiling so a busy container hands out less than an idle one.
    """
    state = state or read_resource_state()
    cpus = state.cpus
    budget = memory_budget(ceiling, state) or ceiling
    per_worker_mb = max(256, int(budget / 1024**2 / max(cpus, 1)))
    return {
        "NODE_OPTIONS": f"--max-old-space-size={per_worker_mb}",
        "VITEST_MAX_THREADS": str(cpus),
        "VITEST_MIN_THREADS": "1",
        "VITEST_MAX_FORKS": str(cpus),
        "UV_THREADPOOL_SIZE": str(min(cpus * 2, 8)),
    }


__all__ = [
    "ResourceState",
    "concurrency_environment",
    "enough_headroom",
    "memory_budget",
    "read_resource_state",
    "usable_cpus",
]
