"""The worker container runs an init as PID 1, so the processes a product's commands orphan are reaped.

Found in review: the worker service ran Celery itself as PID 1. A product's
test servers and the children of a command whose parent exited are handed to
PID 1 when they are orphaned, and Celery never waits for processes it did not
start, so each one stayed a zombie - in the process table, holding a PID
against the container's limit - for the container's life.
"""

from __future__ import annotations

import re
from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def _the_service(name: str) -> str:
    text = COMPOSE.read_text()
    start = text.index(f"\n  {name}:\n")
    following = re.search(r"\n  [A-Za-z0-9_-]+:\n|\n[A-Za-z]", text[start + 1:])
    return text[start: start + 1 + following.start()] if following else text[start:]


def test_the_worker_runs_an_init_that_reaps_orphans():
    worker = _the_service("worker")

    assert re.search(r"^    init: true$", worker, re.MULTILINE), "the worker service sets `init: true`"
    assert "celery" in worker, "and it is the service that runs Celery"
