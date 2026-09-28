"""Refuse a command that would take the run down, instead of being killed.

Run-a000000c was OOM-killed twice. Neither ended as a failure: the kernel kills
the process that would have written the error, so the run was simply orphaned,
and the second kill happened at 8 GiB after the limit had been raised from 4 -
because the multiplier was wrong, not the ceiling. A test runner forked one
worker per *reported* CPU, and a cgroup CPU quota does not change what `nproc`
reports.

The remedy is not a bigger number. It is asking what is free before starting.
"""

from __future__ import annotations

import pytest

from app.tools.resources import (
    ResourceState,
    concurrency_environment,
    enough_headroom,
    memory_budget,
    read_resource_state,
)

GiB = 1024**3


def _state(limit=8 * GiB, in_use=GiB, cpus=2, oom=0) -> ResourceState:
    return ResourceState(
        memory_limit=limit, memory_in_use=in_use, memory_peak=in_use,
        oom_kills=oom, cpus=cpus, pids_in_use=61,
    )


def test_an_idle_container_gets_the_configured_ceiling():
    assert memory_budget(GiB, _state(in_use=256 * 1024**2)) == GiB


def test_a_busy_container_gets_less_than_the_ceiling():
    """The static number was true of each process; the tree was twenty of them."""
    budget = memory_budget(4 * GiB, _state(in_use=int(6.5 * GiB)))

    assert 0 < budget < 4 * GiB


def test_a_nearly_full_container_refuses_rather_than_risking_the_run():
    viable, why = enough_headroom(GiB, _state(in_use=int(7.8 * GiB)))

    assert not viable
    assert "Not enough memory" in why


def test_the_refusal_names_the_numbers_and_what_to_do():
    """A refusal a model cannot act on just moves the failure one step later."""
    _, why = enough_headroom(GiB, _state(in_use=int(7.9 * GiB)))

    assert "headroom" in why
    assert "one test file rather than the suite" in why
    assert "docker-compose.yml" in why


def test_a_reserve_is_kept_for_the_worker_itself():
    """The launching process keeps growing while the command runs - it is
    streaming model output into the same container."""
    state = _state(in_use=int(7.4 * GiB))  # ~600 MiB free

    assert memory_budget(GiB, state) == 0


def test_no_cgroup_limit_means_do_not_restrict():
    """On a developer machine nothing is limited, and refusing to run because a
    limit could not be read would make the sandbox unusable."""
    unknown = ResourceState(None, None, None, 0, 4, None)

    assert memory_budget(GiB, unknown) == GiB
    assert enough_headroom(GiB, unknown)[0] is True


def test_the_heap_is_divided_by_the_cpus_that_will_fork():
    """`--max-old-space-size` applies per worker, so the tree is heap x workers.
    Setting it from the ceiling alone is what let twenty workers reach 8 GiB."""
    environment = concurrency_environment(2 * GiB, _state(cpus=4, in_use=256 * 1024**2))

    per_worker = int(environment["NODE_OPTIONS"].rsplit("=", 1)[1])

    assert environment["VITEST_MAX_FORKS"] == "4"
    assert per_worker * 4 <= 2 * GiB / 1024**2


def test_a_quota_of_two_is_not_the_hosts_twenty():
    environment = concurrency_environment(GiB, _state(cpus=2))

    assert environment["VITEST_MAX_THREADS"] == "2"
    assert environment["UV_THREADPOOL_SIZE"] == "4"


def test_an_earlier_kill_is_visible_after_the_fact():
    """A worker that vanished leaves no exception - only this counter."""
    assert _state(oom=3).was_oom_killed
    assert not _state().was_oom_killed


def test_reading_the_real_cgroup_never_raises():
    """Resource introspection that fails a run is worse than the problem."""
    state = read_resource_state()

    assert isinstance(state.cpus, int) and state.cpus >= 1
    assert isinstance(state.oom_kills, int)
    state.describe()  # must not raise whatever came back


def test_unknown_fields_describe_as_unknown_not_zero():
    """Reporting an unreadable limit as 0 would read as "nothing available"."""
    described = ResourceState(None, None, None, 0, 2, None).describe()

    assert "unknown" in described


def test_the_sandbox_checks_headroom_before_it_launches():
    import inspect

    from app.tools.sandbox import SandboxExecutor

    source = inspect.getsource(SandboxExecutor._run)

    assert "enough_headroom" in source


def test_the_sandbox_reads_its_cpu_count_from_one_place():
    """Two readers of the same fact drift; the pre-flight check and the child
    environment must agree."""
    import inspect

    from app.tools import sandbox

    assert "from app.tools.resources import usable_cpus" in inspect.getsource(
        sandbox._usable_cpus
    )


def test_two_runs_in_one_container_share_one_budget():
    """The worker runs `--concurrency=2`, so two runs share one cgroup.

    `memory.current` is their combined usage, so a budget computed from it is
    already the shared budget - when one run is heavy the other is told there
    is little room, without either knowing the other exists. No caller has to
    know the worker count, which is what would have made this wrong the moment
    the setting changed.
    """
    idle = memory_budget(2 * GiB, _state(in_use=512 * 1024**2))
    crowded = memory_budget(2 * GiB, _state(in_use=6 * GiB))

    assert idle == 2 * GiB
    assert crowded < idle
