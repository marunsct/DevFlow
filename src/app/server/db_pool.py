"""Borrowing a connection from a psycopg2 pool so that a dead one is never handed out twice (harness review HR2.RT.1).

After a Postgres restart every connection the pools held was dead, and each was lent out again: the first request
on each failed, and a connection broken mid-use went back to the pool to fail the next borrower too. A connection
idle for a while is checked with one cheap query before it is lent, and replaced once if it is dead; one that breaks
while lent is closed on its way back instead of being kept.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)

#: A connection idle this long is checked before it is lent: a restart kills idle connections without a word.
CHECK_AFTER_IDLE_SECONDS = 30.0
_LAST_USED: dict[int, float] = {}


def _broken_errors() -> tuple[type[BaseException], ...]:
    try:
        import psycopg2

        return (psycopg2.OperationalError, psycopg2.InterfaceError)
    except ImportError:  # pragma: no cover - psycopg2 is a dependency of every store that pools
        return ()


def _alive(conn: Any) -> bool:
    if getattr(conn, "closed", 0):
        return False
    if time.monotonic() - _LAST_USED.get(id(conn), 0.0) < CHECK_AFTER_IDLE_SECONDS:
        return True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.rollback()
        return True
    except _broken_errors():
        return False


def _a_live_connection(pool: Any) -> Any:
    conn = pool.getconn()
    if _alive(conn):
        return conn
    logger.warning("A pooled database connection was dead (the server restarted?); replacing it")
    _LAST_USED.pop(id(conn), None)
    pool.putconn(conn, close=True)
    return pool.getconn()


@contextmanager
def borrowed(pool: Any) -> Iterator[Any]:
    """A connection from `pool`, rolled back and returned after; closed instead when it broke while lent."""
    conn = _a_live_connection(pool)
    broken = False
    try:
        yield conn
    except _broken_errors():
        broken = True
        raise
    except Exception:
        try:
            conn.rollback()
        except _broken_errors():
            broken = True
        raise
    finally:
        if not broken:
            try:
                conn.rollback()
            except _broken_errors():
                broken = True
            except Exception:  # noqa: BLE001 - a rollback that fails for another reason leaves the connection usable
                pass
        if broken or getattr(conn, "closed", 0):
            _LAST_USED.pop(id(conn), None)
            pool.putconn(conn, close=True)
        else:
            _LAST_USED[id(conn)] = time.monotonic()
            pool.putconn(conn)


__all__ = ["CHECK_AFTER_IDLE_SECONDS", "borrowed"]
