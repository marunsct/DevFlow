"""Which runs a worker task is driving right now, so nothing rewrites a run while its last step is still finishing.

Measured on 2026-11-07: a run was paused, its status read "paused", and it was rewound to an earlier stage. Its worker
task was still inside a model call; the call returned nine seconds later, the stage finished and wrote its checkpoint
over the rewind's, and the resumed run carried on from the abandoned branch - the stage it was rewound to never ran.
A pause is honoured at the next stage boundary; the step in flight still completes. So the worker holds a key for
the run while it drives it, refreshed while it lives, and a rewind waits until the key is gone.
"""
from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Iterator
from typing import Any

logger = logging.getLogger(__name__)

#: How long a key outlives its last refresh: a worker that died stops holding its runs within this.
HELD_FOR_SECONDS = 180
REFRESH_EVERY_SECONDS = 60
#: How long a rewind waits for the step in flight to finish - a long model call.
WAIT_SECONDS = 600


def _key(run_id: str) -> str:
    return f"run-driving:{run_id}"


def _client() -> Any:
    from app.server.redis_client import get_redis_client

    return get_redis_client()


@contextlib.contextmanager
def driving(run_id: str, client: Any = None) -> Iterator[None]:
    """Hold `run_id` while the block runs; never raises for the key's sake."""
    stop = threading.Event()
    try:
        client = client or _client()
        client.set(_key(run_id), str(time.time()), ex=HELD_FOR_SECONDS)
    except Exception:  # noqa: BLE001 - a run is never held back by its marker
        logger.debug("Could not mark run %s as driven", run_id, exc_info=True)
        client = None

    def refresh() -> None:
        while not stop.wait(REFRESH_EVERY_SECONDS):
            try:
                client.expire(_key(run_id), HELD_FOR_SECONDS)
            except Exception:  # noqa: BLE001
                logger.debug("Could not refresh run %s's marker", run_id, exc_info=True)

    keeper = threading.Thread(target=refresh, name=f"driving-{run_id}", daemon=True) if client else None
    if keeper:
        keeper.start()
    try:
        yield
    finally:
        stop.set()
        if client is not None:
            try:
                client.delete(_key(run_id))
            except Exception:  # noqa: BLE001
                logger.debug("Could not release run %s's marker", run_id, exc_info=True)


def held(run_id: str, client: Any = None) -> bool:
    """Whether a worker task is driving `run_id`; False when that cannot be read."""
    try:
        return bool((client or _client()).exists(_key(run_id)))
    except Exception:  # noqa: BLE001 - unreadable is not held: a rewind is not blocked by a missing Redis
        return False


def wait_until_free(run_id: str, seconds: float = WAIT_SECONDS, client: Any = None, poll: float = 2.0) -> bool:
    """Wait until no worker drives `run_id`; whether it came free within `seconds`."""
    deadline = time.monotonic() + seconds
    while held(run_id, client):
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll)
    return True


__all__ = ["HELD_FOR_SECONDS", "WAIT_SECONDS", "driving", "held", "wait_until_free"]
