"""A value that belongs to the process that built it, never to a forked child.

A database connection is a socket, and `fork()` copies the file descriptor, so
a pool built in a parent is still "there" in every child forked after it. Two
processes then speak one wire protocol over one connection. The server sees an
interleaved stream it cannot parse and drops the connection, and whichever
process writes next fails.

Observed on 2026-09-30 in `worker`. After a deploy, the orphan sweep resumed an
abandoned run from the Celery *main* process. That built a runner, and with it a
checkpointer pool, in the parent. A run cancelled afterwards had its pool
process replaced; the replacement was forked from that parent and inherited the
pool. Six Postgres sockets were open in both pid 1 and the new child. Nine
minutes into the next run, a checkpoint write failed:

    psycopg.OperationalError: consuming input failed: server closed the
    connection unexpectedly

and the run was marked failed. Nothing in the run caused it.

Closing an inherited pool in the child is as wrong as using it. Closing sends
the server a Terminate over the parent's socket and kills the parent's
connection instead. So an inherited value is dropped, not closed, and a fresh
one is built for this process.
"""
from __future__ import annotations

import os
import threading
from typing import Callable, Generic, Optional, TypeVar

T = TypeVar("T")


class PerProcess(Generic[T]):
    """Hold one value per process; a child forked later never sees the parent's."""

    def __init__(self) -> None:
        self._value: Optional[T] = None
        self._owner: Optional[int] = None
        self._lock = threading.Lock()

    def get(self, build: Callable[[], T]) -> T:
        """Return this process's value, building it on first use here."""
        with self._lock:
            if self._value is None or self._owner != os.getpid():
                self._value = build()
                self._owner = os.getpid()
            return self._value

    def mine(self) -> Optional[T]:
        """This process's value, or None - never one inherited through fork."""
        return self._value if self._owner == os.getpid() else None

    def take(self) -> Optional[T]:
        """Forget the value and return it only if this process may close it.

        One inherited from a parent is forgotten and not returned: closing it
        here would close the parent's connections.
        """
        with self._lock:
            value = self.mine()
            self._value = None
            self._owner = None
            return value


def owned_here(owner_pid: Optional[int]) -> bool:
    """Whether a value recorded as built by `owner_pid` belongs to this process."""
    return owner_pid == os.getpid()


__all__ = ["PerProcess", "owned_here"]
