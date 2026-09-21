"""The orphan sweep's healthy outcome is not logged as a warning.

`recover_orphaned_runs` is a CLI command that narrates with `print`. The worker
also calls it, on a startup thread, and Celery's `redirect_stdouts` captures
`print` at WARNING - so every worker start logged

    [WARNING/MainProcess] No orphaned runs; every running row has a live task.

which is the *healthy* outcome. Observed on 2026-09-21 on this deployment.

A line that means "everything is fine", arriving at the level reserved for
things that are not, is how a log stops being read: the next real warning is in
a stream the operator has already learnt to skim. The plan makes the same
argument about `/metrics` reporting zeros - an instrument that lies about the
healthy case is worse than no instrument.
"""

from __future__ import annotations

import inspect


def test_the_recovery_function_takes_an_output_sink():
    from app.server.manage import recover_orphaned_runs

    assert "emit" in inspect.signature(recover_orphaned_runs).parameters


def test_it_still_prints_by_default_for_the_cli():
    """The CLI is the primary caller; its behaviour must not change."""
    from app.server.manage import recover_orphaned_runs

    assert inspect.signature(recover_orphaned_runs).parameters["emit"].default is print


def test_the_worker_passes_a_logger_rather_than_print():
    from app.server import tasks

    source = inspect.getsource(tasks._sweep_for_abandoned_runs)
    assert "emit=logger.info" in source, (
        "the worker's sweep still narrates through print, which Celery logs at WARNING"
    )


def test_nothing_in_the_recovery_path_still_calls_print():
    """A `print` left behind reaches the log at WARNING regardless of `emit`."""
    from app.server.manage import recover_orphaned_runs

    source = inspect.getsource(recover_orphaned_runs)
    assert "print(" not in source, "a print survived the emit conversion"


def test_the_healthy_message_goes_to_the_sink():
    """The specific line that was arriving as a warning."""
    from app.server.manage import recover_orphaned_runs

    source = inspect.getsource(recover_orphaned_runs)
    assert 'emit("No orphaned runs' in source
