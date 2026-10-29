"""One OOM kill stops the resumes of the runs it orphaned, not every resume for the rest of the container's life.

Found in review: `_worker_ran_out_of_memory` read the cgroup's `oom_kill`
count and answered "yes" whenever it was above zero. The count only grows
until the container is replaced, so after one OOM kill every later sweep -
including those for runs a deploy orphaned hours later - resumed nothing, and
each such run stayed failed until the next deploy. Now a rise in the count
since the last look is what counts, and it stays the cause for a few minutes:
long enough for the sweeps that judge the runs that one kill orphaned.

The same review found the resumed-once memory kept for the worker's life: a
run resumed once and stopped again hours later, after hours of progress, was
never resumed again.
"""

from __future__ import annotations

import builtins

import pytest

from app.server import manage


@pytest.fixture(autouse=True)
def _a_fresh_count(monkeypatch):
    monkeypatch.setattr(manage, "_OOM_KILLS_LAST_COUNTED", 0, raising=False)
    monkeypatch.setattr(manage, "_OOM_KILL_LAST_SEEN_AT", None, raising=False)
    manage._RESUMED_ON_START.clear()
    yield
    manage._RESUMED_ON_START.clear()


@pytest.fixture
def cgroup(tmp_path, monkeypatch):
    """The cgroup's `memory.events`, as a file the test writes the kill count into."""
    events = tmp_path / "memory.events"
    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if str(path).startswith("/sys/fs/cgroup"):
            return real_open(events, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    def kills(count: int) -> None:
        events.write_text(f"low 0\nhigh 0\nmax 0\noom 0\noom_kill {count}\n")

    return kills


def test_a_kill_is_the_cause_while_it_is_current_and_not_after(cgroup):
    cgroup(3)
    window = manage.OOM_KILL_STAYS_CURRENT_SECONDS

    assert manage._worker_ran_out_of_memory(clock=lambda: 1000.0) is True
    assert manage._worker_ran_out_of_memory(clock=lambda: 1090.0) is True, "the next sweep judges the same kill"
    assert manage._worker_ran_out_of_memory(clock=lambda: 1000.0 + window + 1) is False
    cgroup(4)
    assert manage._worker_ran_out_of_memory(clock=lambda: 1000.0 + window + 2) is True, "a new kill counts again"


def test_a_count_that_never_rose_is_no_kill(cgroup):
    cgroup(0)

    assert manage._worker_ran_out_of_memory(clock=lambda: 50.0) is False


def test_an_unreadable_cgroup_is_no_kill(monkeypatch):
    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if str(path).startswith("/sys/fs/cgroup"):
            raise OSError("no cgroup here")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    assert manage._worker_ran_out_of_memory(clock=lambda: 50.0) is False


def test_a_resume_is_remembered_for_a_while_and_then_forgotten(monkeypatch):
    resumed: list[str] = []
    monkeypatch.setattr(manage, "_resume_one", resumed.append)
    monkeypatch.setattr(manage, "_worker_ran_out_of_memory", lambda: False)
    monkeypatch.delenv("RESUME_ORPHANS_ON_START", raising=False)

    assert manage.resume_runs_a_restart_abandoned(["run-one"]) == 1
    assert manage.resume_runs_a_restart_abandoned(["run-one"]) == 0, "a crash loop costs one repeat"

    manage._RESUMED_ON_START["run-one"] -= manage.RESUMED_ONCE_REMEMBERED_SECONDS + 1

    assert manage.resume_runs_a_restart_abandoned(["run-one"]) == 1
    assert resumed == ["run-one", "run-one"]
