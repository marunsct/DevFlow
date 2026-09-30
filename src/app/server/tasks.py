"""Celery worker entry point for workflow execution.

Three things this module gets deliberately right, having previously got them
wrong:

- **Shared resources live for the worker process, not the task.** A store and an
  event bus are built once per process. Constructing them per task opened a new
  20-connection Postgres pool every time and never closed it, which exhausted the
  database after a few dozen tasks.
- **Time limits exist.** A hung provider call used to pin a worker slot forever.
- **Retries do not repeat side effects.** The workflow writes files and spends
  tokens, so a blanket retry of the whole segment was not safe. Only genuinely
  transient infrastructure failures are retried; anything else marks the run
  failed for a human to resume deliberately.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from celery import Celery
from celery.signals import (
    task_failure,
    task_prerun,
    worker_process_init,
    worker_process_shutdown,
    worker_ready,
)

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("langchain_tasks", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    # A workflow segment writes files and calls paid APIs, so it must not be
    # silently re-run when a worker dies mid-task. The run is left in a state a
    # human can inspect and resume instead.
    task_acks_late=False,
    task_reject_on_worker_lost=False,
    # One dispatch runs the graph until it pauses or finishes, and on an
    # unattended run that means the *whole* workflow: a dozen stages, each a
    # sequence of model calls. Against a local model that is hours of work, and
    # the old hour-long ceiling cut it off mid-stage - measured on one run,
    # 54.3 minutes of healthy progress from stack_selector to technical_lead,
    # then SoftTimeLimitExceeded with the specialists still ahead of it.
    #
    # The limit still exists to reclaim a worker from a task that is genuinely
    # wedged; it is sized for the work rather than for an API-latency workload.
    # Nothing is lost when it fires - the graph checkpoints at every node
    # boundary and the run resumes from the last one - but each cut costs a
    # manual resume, so the ceiling should be reached only by a real hang.
    task_time_limit=int(os.environ.get("CELERY_TASK_TIME_LIMIT", "21900")),
    task_soft_time_limit=int(os.environ.get("CELERY_TASK_SOFT_TIME_LIMIT", "21600")),
    worker_max_tasks_per_child=int(os.environ.get("CELERY_MAX_TASKS_PER_CHILD", "50")),
    broker_connection_retry_on_startup=True,
)

# Failures that are worth retrying: the work never started, or the infrastructure
# blinked. Anything else is a logic or model failure that retrying will reproduce.
_RETRYABLE = (ConnectionError, TimeoutError, OSError)

_runner = None
#: The pid that built `_runner`. See `_get_runner`.
_runner_owner: int | None = None


#: How long the recovery lock is held. Long enough that a second worker
#: starting beside this one does not repeat the work, short enough that a
#: worker killed mid-recovery does not block the next start for long.
_RECOVERY_LOCK_SECONDS = 120


@worker_ready.connect
def _recover_runs_their_worker_abandoned(**_kwargs) -> None:
    """Unstick runs whose worker died, once, when a worker comes up.

    A run is handed to one Celery task and the row says `running` for as long
    as that task lives. `task_acks_late=False`, so a worker that dies mid-task
    never has it redelivered: nothing writes a terminal status and the row
    says `running` for ever. `resume_run` compare-and-sets from `failed` and
    refuses; `reconcile-runs` deliberately leaves unattended runs alone. The
    work is all still on disk - the graph checkpoints at every node boundary -
    and nothing can reach it.

    That was already known and already fixed, as a command an operator has to
    remember to type. Nothing called it. Measured on 2026-09-19 against the
    live database: of the forty most recent failed runs, twenty carried "The
    worker running this stage stopped without finishing", and one run had sat
    at `running` since the container was replaced eight hours earlier while
    reporting healthy to every caller that asked.

    A worker restart is not an exceptional event here. It happens on every
    deploy, every OOM and every configuration change, and runs last hours. So
    the repair belongs where the restart is observed rather than in an
    operator's memory.

    Safety is inherited unchanged from `recover_orphaned_runs`: a run is only
    touched when a worker answered the broker and did not claim its task. If
    no worker answers, nothing is judged orphaned. Marking the row `failed` is
    what makes `resume` able to reach it again; it does not discard the work.

    Never raises. A worker that cannot run this must still accept tasks.
    """
    if os.environ.get("RECOVER_ORPHANS_ON_START", "true").strip().lower() in {
        "0", "false", "no", "off",
    }:
        return
    try:
        from app.server.redis_client import get_redis_client

        # One worker per restart does the sweep. `nx` makes this a lock rather
        # than a race: several workers come up together on every deploy.
        client = get_redis_client()
        if not client.set("harness:recover-orphans", "1", nx=True, ex=_RECOVERY_LOCK_SECONDS):
            logger.info("Another worker is recovering abandoned runs; skipping")
            return
    except Exception:  # noqa: BLE001 - no lock is a reason to skip, not to crash
        logger.warning("Could not take the orphan-recovery lock; skipping", exc_info=True)
        return

    # Off the startup path, and not immediately.
    #
    # `worker_ready` fires the moment this worker will accept tasks, which is
    # before it can answer a broadcast `inspect.active` about itself. The
    # first version ran the sweep inline and was answered "No worker answered,
    # so nothing can be judged orphaned. Nothing changed." - measured on the
    # deploy at 04:36 - so it never repaired anything. The safety property
    # held; the feature did not exist.
    #
    # A daemon thread, because blocking here delays the worker accepting work,
    # and the sweep is worth seconds of patience rather than none.
    import threading

    threading.Thread(
        target=_sweep_for_abandoned_runs, name="orphan-sweep", daemon=True
    ).start()


#: How long to give this worker to become answerable on the broker before
#: believing "no worker answered". Retried rather than slept once, because the
#: delay that matters is registration, not a fixed duration.
_SWEEP_ATTEMPTS = 6
_SWEEP_INTERVAL_SECONDS = 5

#: How long the sweep waits before looking a second time. Sized to the grace
#: `recover_orphaned_runs` gives a recently-touched run, because that is exactly
#: what the second look is for: a run inside the window on the first pass has to
#: be judged once it leaves it. A module constant so a test can shorten it -
#: blocking a daemon thread for two minutes is free in a worker and is not free
#: in a test suite.
_SECOND_SWEEP_DELAY_SECONDS: float | None = None


def _sweep_for_abandoned_runs() -> None:
    """Run the orphan sweep once the broker can answer. Never raises."""
    import time

    from app.server.manage import (
        RECENTLY_TOUCHED_SECONDS,
        _live_task_ids,
        recover_orphaned_runs,
    )

    for attempt in range(_SWEEP_ATTEMPTS):
        time.sleep(_SWEEP_INTERVAL_SECONDS)
        try:
            if _live_task_ids() is None:
                # Not "nothing is running" - "cannot tell yet". The difference
                # is the whole safety property; see `_live_task_ids`.
                continue
            # `logger.info`, not the default `print`: this runs on a worker
            # startup thread, where Celery's `redirect_stdouts` turns every
            # `print` into a WARNING. The healthy outcome was being logged as a
            # warning on every worker start.
            # The grace belongs here, not in the function's default: this is
            # the caller that guesses, from a broker reply that can be
            # incomplete seconds after a hand-off. See
            # `RECENTLY_TOUCHED_SECONDS`.
            recover_orphaned_runs(
                dry_run=False, emit=logger.info,
                grace_seconds=RECENTLY_TOUCHED_SECONDS,
            )
            # Once more, after the grace window a freshly-dispatched run is
            # protected by. A run that is genuinely gone stops touching its row,
            # so it is still caught; one that is working has moved on and is
            # skipped again. Without this second look, a run abandoned moments
            # before the worker restarted would stay `running` for ever, which
            # is the state this sweep exists to clear.
            delay = (
                RECENTLY_TOUCHED_SECONDS
                if _SECOND_SWEEP_DELAY_SECONDS is None
                else _SECOND_SWEEP_DELAY_SECONDS
            )
            time.sleep(delay)
            try:
                recover_orphaned_runs(
                    dry_run=False, emit=logger.info,
                    grace_seconds=RECENTLY_TOUCHED_SECONDS,
                )
            except Exception:  # noqa: BLE001 - a sweep must never take a worker down
                logger.warning("Second orphan sweep failed", exc_info=True)
            return
        except Exception:  # noqa: BLE001 - a sweep must never take a worker down
            logger.warning("Could not recover abandoned runs", exc_info=True)
            return
    logger.warning(
        "No worker answered the broker after %d attempts; abandoned runs were "
        "not swept. Run `manage.py recover-orphans` by hand if a run is stuck "
        "at `running` with nothing executing.",
        _SWEEP_ATTEMPTS,
    )


@worker_process_init.connect
def _init_worker_process(**_kwargs) -> None:
    """Build the per-process runner once, after fork."""
    global _runner

    # This process makes every model call, so it is where a proxy origin error
    # shows up. Installing the observer here turns a bare `524` in the log into
    # a sentence naming the cause. See `app.observability.proxy_timeouts`.
    from app.observability.proxy_timeouts import install as _install_proxy_diagnostics

    _install_proxy_diagnostics()
    from app.server.events import EventBus
    from app.server.run_store import RunStore
    from app.server.runner import WorkflowRunner

    global _runner_owner
    _runner = WorkflowRunner(event_bus=EventBus(), run_store=RunStore.shared())
    _runner_owner = os.getpid()
    logger.info("Worker process initialised")


@task_prerun.connect
def _install_diagnostics_once_logging_is_up(**_kwargs) -> None:
    """Re-attach the proxy-timeout observer now Celery's handlers exist.

    `worker_process_init` fires before Celery finishes installing its logging
    handlers, so an observer attached there sees the `httpx` logger and no
    handlers at all. `install()` is idempotent per target, so calling it again
    here costs nothing and picks up the handlers that appeared in between.
    Verified on 2026-09-21: attached only at process init, two live `524`
    responses went past without the diagnostic firing.
    """
    try:
        from app.observability.proxy_timeouts import install

        install()
    except Exception:  # noqa: BLE001 - a diagnostic must never fail a task
        logger.debug("Could not install the proxy-timeout observer", exc_info=True)


@worker_process_shutdown.connect
def _shutdown_worker_process(**_kwargs) -> None:
    from app.server.run_store import RunStore

    RunStore.reset_shared()


def _get_runner():
    """Return this process's runner, building it if a signal did not fire.

    One built in another process is never returned. The orphan sweep runs in
    the Celery parent and builds a runner there; a worker forked from it later
    must not drive runs through the parent's connections.
    """
    global _runner
    if _runner is None or _runner_owner != os.getpid():
        _init_worker_process()
    return _runner


@task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, **_other):
    """Record a permanently failed task on the dead-letter list."""
    from app.server.redis_client import get_redis_client

    try:
        client = get_redis_client()
        client.lpush(
            "celery_dlq",
            json.dumps(
                {
                    "task_id": task_id,
                    "task_name": getattr(sender, "name", "unknown"),
                    "exception": str(exception),
                    "kwargs": kwargs,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
        )
        # Bounded, so a persistent failure cannot fill Redis.
        client.ltrim("celery_dlq", 0, 999)
    except Exception:  # noqa: BLE001
        logger.error("Failed to write to the dead-letter queue", exc_info=True)


def _mark_failed(run_id: str, message: str) -> None:
    from app.server.run_store import RunStore

    try:
        store = RunStore.shared()
        record = store.load(run_id)
        if record is None:
            return
        record.status = "failed"
        record.error = message[:500]
        record.updated_at = datetime.now(timezone.utc).isoformat()
        store.save(record)
    except Exception:  # noqa: BLE001
        logger.error("Could not mark run %s as failed", run_id, exc_info=True)


# `ignore_result` because nothing reads one. The run's state lives in the run
# store, which is what every caller queries; no `AsyncResult` is constructed
# anywhere in `app.server`. Storing a result was therefore write-only - until a
# cancellation made it worse than useless.
#
# `cancel_run` revokes with `terminate=True, signal="SIGTERM"`, which raises
# `SystemExit` inside the pool child. Celery then tries to store that exception
# as the task's result, and the JSON serializer cannot encode it. Measured on
# 2026-09-20, cancelling one run:
#
#     Pool callback raised exception: EncodeError(
#         TypeError('Object of type SystemExit is not JSON serializable'))
#
# followed by two full tracebacks, for a cancellation that had already been
# recorded correctly in the database. The run was fine; the log said otherwise,
# and a concurrent run on the same worker was left looking like the suspect.
@celery_app.task(
    bind=True, name="execute_workflow_run", max_retries=2, ignore_result=True
)
def execute_workflow_run(
    self,
    run_id: str,
    resume: bool = False,
    decision_payload: dict | None = None,
) -> None:
    """Run one segment of a workflow graph."""
    runner = _get_runner()
    record = runner.run_store.load(run_id)
    if record is None:
        logger.error("Run %s not found; nothing to execute", run_id)
        return

    if runner.run_store.is_cancel_requested(run_id):
        logger.info("Run %s was cancelled before execution started", run_id)
        return

    if decision_payload:
        record.pending_decision_payload = decision_payload

    document = None
    if record.document_paths and not resume:
        from app.documents import read_document

        try:
            document = read_document(record.document_paths)
        except Exception as exc:  # noqa: BLE001
            _mark_failed(run_id, f"Could not read the uploaded documents: {exc}")
            return

    repository = None
    if record.repo_root:
        from app.tools.repository import build_repository_context

        try:
            repository = build_repository_context(record.repo_root, allow_subdirectories=True)
        except Exception as exc:  # noqa: BLE001
            _mark_failed(run_id, f"Could not prepare the workspace: {exc}")
            return

    try:
        # asyncio.run gives each task its own loop and closes it afterwards.
        # get_event_loop() was deprecated in this position and raises outright
        # under the threads and gevent worker pools.
        asyncio.run(runner._run_loop(record, document, repository, resume=resume))
    except _RETRYABLE as exc:
        if self.request.retries < self.max_retries:
            countdown = 5 * (2**self.request.retries)
            logger.warning(
                "Transient failure on run %s (attempt %s); retrying in %ss",
                run_id, self.request.retries + 1, countdown,
            )
            raise self.retry(exc=exc, countdown=countdown)
        _mark_failed(run_id, f"Infrastructure failure after retries: {exc}")
        raise
    except Exception as exc:  # noqa: BLE001
        # _run_loop already records the failure; this catches anything raised
        # outside it. Not retried: re-running would duplicate file writes and
        # model spend.
        logger.exception("Run %s failed permanently", run_id)
        _mark_failed(run_id, f"{type(exc).__name__}: {exc}")
        raise


__all__ = ["celery_app", "execute_workflow_run"]
