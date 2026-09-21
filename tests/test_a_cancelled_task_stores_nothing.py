"""Cancelling a run must not leave an unserializable result behind.

`cancel_run` revokes the worker task with `terminate=True, signal="SIGTERM"`,
which raises `SystemExit` inside the pool child. If the task stores a result,
Celery tries to encode that exception as JSON and cannot:

    Pool callback raised exception: EncodeError(
        TypeError('Object of type SystemExit is not JSON serializable'))

Measured on 2026-09-20 cancelling run 9c0fc48d, which produced that line and two
full tracebacks for a cancellation the database had already recorded correctly.
A concurrent run on the same worker was still healthy and looked like the cause.

Nothing reads a result: the run store is what every caller queries, and no
`AsyncResult` is constructed anywhere in `app.server`.
"""

from __future__ import annotations

from pathlib import Path


def test_the_workflow_task_stores_no_result():
    from app.server.tasks import execute_workflow_run

    assert execute_workflow_run.ignore_result is True, (
        "a terminated task will try to store SystemExit and fail to encode it"
    )


def test_nothing_reads_a_task_result():
    """The claim the setting rests on, checked rather than remembered.

    If a caller ever does need one, this test fails and says so, instead of
    `ignore_result` quietly making the result always `None`.
    """
    # Resolved from this file, not from the working directory: a neighbouring
    # test that chdir's would otherwise make this pass or fail by accident.
    server = Path(__file__).resolve().parents[1] / "src" / "app" / "server"
    assert server.is_dir()

    # `AsyncResult(` - the construction, not the word. The first version
    # searched for the bare name and matched the comment in `tasks.py` that
    # explains why nothing constructs one, so the test failed on its own
    # documentation.
    offenders = [
        path.name
        for path in server.rglob("*.py")
        if "AsyncResult(" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"these read a task result: {offenders}"
