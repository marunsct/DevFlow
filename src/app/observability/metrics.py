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
from pathlib import Path
from typing import Dict, Any

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

logger = logging.getLogger(__name__)


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

    def _on_exit() -> None:
        # Not a delete: counters from a dead process are still part of the
        # total. This tells prometheus_client the process is gone so it can
        # treat its gauge files correctly.
        try:
            from prometheus_client import multiprocess

            multiprocess.mark_process_dead(os.getpid(), directory)
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

def get_metrics_payload() -> tuple[bytes, str]:
    """
    Returns the prometheus metrics payload and content type.
    Suitable for serving on a /metrics HTTP endpoint.
    """
    return generate_latest(), CONTENT_TYPE_LATEST
