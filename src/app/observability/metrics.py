"""Prometheus counters for the workflow, shared across the app and the worker.

**Why this module configures multiprocess mode.** The recorders are called from
two different containers. `record_run` runs in the API process (`start_run`);
`record_stage_duration` and `record_defect_resolution` run in the Celery worker,
which is where the graph actually executes. `/metrics` is served by the API.

With a per-process registry that means the endpoint can only ever report the one
counter the API happens to increment itself: observed on 2026-09-21 during a
live run, `/metrics` served `run_total 1.0` and a `stage_duration_seconds`
histogram with no samples at all, while the worker was several stages in.

That is the exact failure plan-part3 §3.1 describes - "a dashboard that reports
`defects_resolved_total 0` on a system that has resolved defects is worse than
no dashboard" - surviving the fix for it, because item 2 wired the recorders and
did not cross the process boundary.

`prometheus_client`'s multiprocess mode is the mechanism. Both containers mount
the same `appdata` volume, so they can share a directory of mmap files, and
`prometheus_fastapi_instrumentator` already builds a `MultiProcessCollector`
when `PROMETHEUS_MULTIPROC_DIR` is set.

**Two things follow from that and are handled here.**

Counters and histograms are cumulative, so files left by an exited process are
still summed and must *not* be deleted on startup - a wipe would reset the very
totals the endpoint exists to report. `mark_process_dead` is called on exit
instead, which is what lets `prometheus_client` collapse a dead process's gauge
files while keeping its counters.

The directory is created here rather than in the image, because both services
need it to exist before the first metric is touched and only one of them owns
the volume's contents.
"""

import atexit
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Dict, Any

from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

#: Distinguishes this run of this process from every previous one. The library
#: names each process's mmap file after `os.getpid()`, and a container's PIDs
#: start from 1 again on every restart, so a fresh process opens the file a
#: long-dead process left behind. When the two disagree about the file's shape
#: the read fails outright:
#:
#:     RuntimeError: Read beyond file size detected, file is corrupted.
#:
#: Measured on one run: that exception 17 times, once per stage, so not one
#: stage duration in the run was recorded. The directory held 49 `.db` files
#: going back three days, named `counter_1.db`, `counter_354.db`,
#: `counter_2673.db` - PIDs from container generations that no longer exist.
#:
#: The directory cannot simply be wiped at startup, for the reason this module
#: already documents: a dead process's counters are still part of the total, and
#: both containers share the volume, so one starting would erase the other's.
#: Making the name unique costs nothing and removes the collision instead of
#: arguing about who may delete what.
_THIS_PROCESS_GENERATION = uuid.uuid4().hex[:8]

#: How long a file left by a process that has exited is still summed into the
#: totals. Without a bound they accumulate for the lifetime of the volume, and
#: every one of them is read on every scrape of `/metrics`.
DAYS_TO_KEEP_A_DEAD_PROCESS_FILE = 7


def _the_identity_of_this_process() -> str:
    """The name this process's metric files carry.

    Must return the same value throughout one process and a different one in a
    forked child - `MultiProcessValue.__check_for_pid_change` calls it on every
    value it creates and reopens the file when the answer changes. The pid is
    what satisfies the fork half; the generation is what stops a later process
    inheriting a dead one's file.
    """
    return f"{_THIS_PROCESS_GENERATION}_{os.getpid()}"


def _discard_unreadable_files(directory: Path) -> None:
    """Remove `.db` files that can no longer be read, and very old ones.

    An unreadable file is not a loss being taken here: it is already lost, and
    leaving it in place fails every scrape of `/metrics` rather than only the
    process that wrote it. Tested by reading, not guessed at from the name.

    Never raises. Metrics must not stop a process starting.
    """
    cutoff = time.time() - DAYS_TO_KEEP_A_DEAD_PROCESS_FILE * 86400
    for path in sorted(directory.glob("*.db")):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                logger.info("Removed stale metric file %s", path.name)
                continue
            from prometheus_client.mmap_dict import MmapedDict

            # Consumed, not merely called: it returns a generator, so calling it
            # alone reads nothing and every corrupt file looks readable. Found by
            # the test that feeds it a corrupt file and then scrapes.
            list(MmapedDict.read_all_values_from_file(str(path)))
        except OSError:  # vanished, or another process holds it; not ours to fix
            continue
        except Exception:  # noqa: BLE001 - unreadable is the case this is for
            try:
                path.unlink()
                logger.warning("Removed unreadable metric file %s", path.name)
            except OSError:
                logger.debug("Could not remove %s", path, exc_info=True)


def _prepare_multiprocess_dir() -> None:
    """Make `PROMETHEUS_MULTIPROC_DIR` usable, and register the exit hook.

    A no-op when the variable is unset, which keeps single-process use (the CLI,
    the tests) on the ordinary in-memory registry.
    """
    directory = os.environ.get("PROMETHEUS_MULTIPROC_DIR", "").strip()
    if not directory:
        return
    try:
        Path(directory).mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001 - metrics must never stop a process starting
        logger.warning("Could not create %s; metrics will be per-process", directory)
        return

    # Before any metric is defined, or the default identifier is already bound
    # into the values created for them.
    try:
        from prometheus_client import values

        values.ValueClass = values.MultiProcessValue(
            process_identifier=_the_identity_of_this_process
        )
    except Exception:  # noqa: BLE001 - the default still works, it just collides
        logger.warning(
            "Could not name this process's metric files uniquely; "
            "a restart may reuse a dead process's file",
            exc_info=True,
        )

    _discard_unreadable_files(Path(directory))

    def _on_exit() -> None:
        # Not a delete: counters from a dead process are still part of the
        # total. This tells prometheus_client the process is gone so it can
        # treat its gauge files correctly. Named with the same identity the
        # files carry, or it would look for a file that was never written.
        try:
            from prometheus_client import multiprocess

            multiprocess.mark_process_dead(_the_identity_of_this_process(), directory)
        except Exception:  # noqa: BLE001
            logger.debug("Could not mark this process dead for metrics", exc_info=True)

    atexit.register(_on_exit)


_prepare_multiprocess_dir()

# Basic Prometheus metrics definitions
DEFECTS_RESOLVED = Counter('defects_resolved_total', 'Total number of defects resolved')
DEFECTS_FAILED = Counter('defects_failed_total', 'Total number of defects failed to resolve')
STAGE_DURATION = Histogram('stage_duration_seconds', 'Time spent in each workflow stage', ['stage'])
RUN_TOTAL = Counter('run_total', 'Total number of agentic workflow runs')

class MetricsTracker:
    @staticmethod
    def record_stage_duration(stage_name: str, duration_seconds: float) -> None:
        STAGE_DURATION.labels(stage=stage_name).observe(duration_seconds)
        
    @staticmethod
    def record_defect_resolution(resolved: bool) -> None:
        if resolved:
            DEFECTS_RESOLVED.inc()
        else:
            DEFECTS_FAILED.inc()
            
    @staticmethod
    def record_run() -> None:
        RUN_TOTAL.inc()
