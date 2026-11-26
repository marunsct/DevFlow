"""One diagnosis of a model at a time, across the runs on this machine; the others wait for its result (LF.1568).

A model not seen before is diagnosed at a run's start (`app.server.tasks`, `app.models.diagnostics`): dozens of
calls - tools, a stage-shaped answer, a 24,000-token recall question, reply salvage, the deep checks - before the
first stage. Two runs started together on a new model each found no kept diagnosis and each ran the whole of it on
the one server at once: twice the calls, each slower for sharing the server, and the second result written over the
first. Now the first run to ask takes the model's turn (a file lock beside the model's kept measurements, so the
worker's processes and threads all see it), and a run that finds it taken waits for it, then reads what was kept.

A holder that dies releases its turn with its process. A wait longer than `WAIT_SECONDS` stops waiting and the run
goes on as before, so a stuck diagnosis never holds a run for good.
"""
from __future__ import annotations

import fcntl
import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

#: The longest a run waits for another run's diagnosis of the same model, in seconds.
WAIT_SECONDS = 1800.0
#: How often a waiting run looks whether the turn is free.
POLL_SECONDS = 0.2

_LOCK = threading.Lock()
#: The models whose turn a thread of this process holds: name -> (thread, depth), so a holder may take it again.
_HELD: dict[str, tuple[int, int]] = {}


def _lock_path(name: str):
    from app.models.registry import _slug, fitness_dir

    folder = fitness_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f".{_slug(name)}.diagnosis.lock"


def _again(name: str) -> bool:
    """Whether this thread holds `name`'s turn already: it takes it again without waiting."""
    me = threading.get_ident()
    with _LOCK:
        holder = _HELD.get(name)
        if holder is not None and holder[0] == me:
            _HELD[name] = (me, holder[1] + 1)
            return True
    return False


def _let_go(name: str) -> None:
    with _LOCK:
        holder = _HELD.get(name)
        if holder is None:
            return
        if holder[1] <= 1:
            _HELD.pop(name, None)
        else:
            _HELD[name] = (holder[0], holder[1] - 1)


@contextmanager
def one_at_a_time(name: str, waiting: Callable[[], None] | None = None) -> Iterator[bool]:
    """Hold `name`'s diagnosis turn for the block; True when held, False when it could not be (no lock file, or the
    wait ran out) - the block runs either way. `waiting` is called once when another run holds the turn."""
    if not name or _again(name):
        try:
            yield bool(name)
        finally:
            if name:
                _let_go(name)
        return
    handle = None
    held = False
    try:
        handle = open(_lock_path(name), "a+")  # noqa: SIM115 - held for the block
        deadline = time.monotonic() + WAIT_SECONDS
        said = False
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held = True
                break
            except BlockingIOError:
                if not said:
                    said = True
                    logger.info("Another run is diagnosing %s; waiting for its result", name)
                    if waiting is not None:
                        try:
                            waiting()
                        except Exception:  # noqa: BLE001 - a note never stops the wait
                            pass
                if time.monotonic() >= deadline:
                    logger.warning("Waited %.0f s for another run's diagnosis of %s; going on", WAIT_SECONDS, name)
                    break
                time.sleep(POLL_SECONDS)
    except OSError:
        logger.debug("Could not take the diagnosis turn of %s", name, exc_info=True)
    if held:
        with _LOCK:
            _HELD[name] = (threading.get_ident(), 1)
    try:
        yield held
    finally:
        if held:
            _let_go(name)
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            except OSError:
                pass
        if handle is not None:
            handle.close()


__all__ = ["POLL_SECONDS", "WAIT_SECONDS", "one_at_a_time"]
