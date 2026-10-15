"""Model calls a deploy waits for, and a hold that keeps new ones from starting.

Owner, 2026-10-15: deploy between model calls - if a call is in progress,
deploy once it is done, then resume. A restart in the middle of a call threw
away a reply the run had already waited minutes for (one local call took
5 minutes) and the stage asked again from its last checkpoint.

Each call registers itself as a file under `<gate>/inflight/` for as long as
it runs. A deploy sets `<gate>/hold`, waits until `inflight/` is empty, and
restarts; a call that would start while the hold is set waits for it to be
lifted, so nothing new begins in the window. The gate lives in the data
volume the app and worker share (`MODEL_CALL_GATE_DIR`).
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

#: How long a call waits for a hold to be lifted before going ahead anyway.
#: A deploy that died with the hold set must not stop every run for good.
MOST_SECONDS_HELD = 20 * 60
POLL_SECONDS = 2.0


def gate_directory() -> Path:
    return Path(os.environ.get("MODEL_CALL_GATE_DIR") or "/app/data/loop/gate")


def held() -> bool:
    try:
        return (gate_directory() / "hold").exists()
    except OSError:
        return False


def in_flight() -> list[str]:
    try:
        return sorted(path.name for path in (gate_directory() / "inflight").iterdir())
    except OSError:
        return []


def _wait_while_held(sleep=time.sleep, clock=time.monotonic) -> None:
    if not held():
        return
    logger.info("A deploy is waiting for model calls to finish; this call starts after it")
    started = clock()
    while held() and clock() - started < MOST_SECONDS_HELD:
        sleep(POLL_SECONDS)


@contextmanager
def a_model_call() -> Iterator[None]:
    """Hold this call while a deploy is pending, then mark it in flight until it returns."""
    _wait_while_held()
    marker = None
    try:
        directory = gate_directory() / "inflight"
        directory.mkdir(parents=True, exist_ok=True)
        marker = directory / f"{os.getpid()}-{uuid.uuid4().hex[:12]}"
        marker.write_text(str(time.time()))
    except OSError:
        marker = None  # a gate that cannot be written never stops a call
    try:
        yield
    finally:
        if marker is not None:
            try:
                marker.unlink()
            except OSError:
                pass
