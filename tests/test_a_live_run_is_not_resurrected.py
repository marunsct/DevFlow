"""A run dispatched moments ago must not be judged abandoned.

`recover_orphaned_runs` decides liveness by asking the broker which task ids it
still knows about, and its own docstring names the danger of getting that wrong:
"guessing wrong here puts two writers on one thread". The guess was still
available to make, because a broker's answer can lag a task it has only just
handed to a pool child.

Measured on run 7c0bf755, 2026-09-21. Dispatched at 15:45:00 as task
`fce6686c`; the worker's startup sweep ran eleven seconds later while that task
was executing. `_live_task_ids()` did answer - so the "no worker replied" guard
did not fire - but the reply did not list the task. The run was marked failed
and resumed as `ed7d5341`, and then ran twice: two executions of one run
interleaving their stages into one workspace and one transcript, contending for
the same model server, with `specialist_ui_ux_0` and `tools_models` alternating
in a graph that cannot do that.

`updated_at` is the liveness signal that does not depend on inspect timing: a
run that has genuinely stopped goes quiet.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.server.manage import RECENTLY_TOUCHED_SECONDS, _touched_within


class _Record:
    def __init__(self, updated_at):
        self.updated_at = updated_at


def _ago(**kwargs) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kwargs)).isoformat()


class TestTheRecencySignal:
    def test_a_run_touched_now_is_protected(self):
        assert _touched_within(_Record(_ago(seconds=1)), RECENTLY_TOUCHED_SECONDS)

    def test_the_eleven_second_window_that_lost_run_7c0bf755(self):
        assert _touched_within(_Record(_ago(seconds=11)), RECENTLY_TOUCHED_SECONDS)

    def test_a_long_dead_run_is_not_protected(self):
        assert not _touched_within(_Record(_ago(hours=3)), RECENTLY_TOUCHED_SECONDS)

    def test_just_past_the_window_is_not_protected(self):
        assert not _touched_within(
            _Record(_ago(seconds=RECENTLY_TOUCHED_SECONDS + 5)),
            RECENTLY_TOUCHED_SECONDS,
        )

    @pytest.mark.parametrize("value", [None, "", "not a date", 12345])
    def test_an_undatable_row_is_judged_as_before(self, value):
        """Protected for ever is worse than judged: it can never be cleared."""
        assert not _touched_within(_Record(value), RECENTLY_TOUCHED_SECONDS)

    def test_a_naive_timestamp_is_read_as_utc(self):
        naive = (datetime.now(timezone.utc) - timedelta(seconds=5)).replace(
            tzinfo=None
        ).isoformat()
        assert _touched_within(_Record(naive), RECENTLY_TOUCHED_SECONDS)


class TestTheWindowIsSizedForTheRace:
    def test_it_covers_the_dispatch_race_generously(self):
        assert RECENTLY_TOUCHED_SECONDS >= 60

    def test_it_is_far_shorter_than_real_abandonment(self):
        assert RECENTLY_TOUCHED_SECONDS <= 600


class TestTheSweepLooksAgain:
    """Skipping is only safe because something checks later.

    A run abandoned moments before the worker restarted is inside the grace
    window on the first pass. Without a second look it would stay `running` for
    ever, which is the state this sweep exists to clear.
    """

    def test_the_sweep_runs_a_second_pass(self):
        import inspect

        from app.server.tasks import _sweep_for_abandoned_runs

        source = inspect.getsource(_sweep_for_abandoned_runs)
        assert source.count("recover_orphaned_runs(") >= 2
        assert "RECENTLY_TOUCHED_SECONDS" in source

    def test_the_second_pass_cannot_take_the_worker_down(self, monkeypatch):
        """It runs on a daemon thread at startup; it may never raise."""
        from app.server import tasks

        monkeypatch.setattr(tasks, "_SWEEP_INTERVAL_SECONDS", 0)
        monkeypatch.setattr(tasks, "_SECOND_SWEEP_DELAY_SECONDS", 0)
        monkeypatch.setattr("app.server.manage._live_task_ids", lambda: {"abc"})

        calls: list[int] = []

        def _explode_on_the_second(dry_run=False, emit=print, grace_seconds=0):
            calls.append(1)
            if len(calls) > 1:
                raise RuntimeError("the database went away")
            return 0

        monkeypatch.setattr(
            "app.server.manage.recover_orphaned_runs", _explode_on_the_second
        )

        tasks._sweep_for_abandoned_runs()  # must not raise

        assert len(calls) == 2

    def test_the_delay_is_sized_to_the_grace(self):
        from app.server.manage import RECENTLY_TOUCHED_SECONDS
        from app.server.tasks import _SECOND_SWEEP_DELAY_SECONDS

        # None means "use the grace itself", which is the point.
        assert _SECOND_SWEEP_DELAY_SECONDS is None
        assert RECENTLY_TOUCHED_SECONDS > 0


def test_the_cli_gets_no_grace_and_the_sweep_does():
    """Two callers asking different questions.

    The sweep guesses, from a broker reply that can be incomplete seconds after
    a hand-off, and that guess is what ran run 7c0bf755 twice. A human running
    `manage.py recover-orphans` has looked and decided, and making them wait
    two minutes to act on their own judgement would answer a question they did
    not ask.
    """
    import inspect

    from app.server.manage import recover_orphaned_runs
    from app.server.tasks import _sweep_for_abandoned_runs

    assert inspect.signature(recover_orphaned_runs).parameters[
        "grace_seconds"
    ].default == 0.0

    source = inspect.getsource(_sweep_for_abandoned_runs)
    assert source.count("grace_seconds=RECENTLY_TOUCHED_SECONDS") == 2


def test_a_recent_run_is_reported_rather_than_silently_skipped():
    """An operator reading the log must see why nothing was repaired."""
    import inspect

    from app.server.manage import recover_orphaned_runs

    source = inspect.getsource(recover_orphaned_runs)
    assert "too recent to call abandoned" in source
    assert "the next sweep will see it" in source
