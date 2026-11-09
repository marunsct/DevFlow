"""A dead pooled database connection is replaced, and one that breaks while lent is not kept (harness review HR2.RT.1).

After a Postgres restart every pooled connection was dead and lent out again: the first request on each failed, and a
connection that broke mid-use went back to the pool for the next borrower.
"""
from __future__ import annotations

import psycopg2
import pytest

from app.server import db_pool


class _Cursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        if self.conn.dead:
            raise psycopg2.OperationalError("server closed the connection unexpectedly")


class _Conn:
    def __init__(self, dead=False):
        self.dead, self.closed = dead, 0

    def cursor(self):
        return _Cursor(self)

    def rollback(self):
        if self.dead:
            raise psycopg2.InterfaceError("connection already closed")


class _Pool:
    def __init__(self, *conns):
        self.free, self.returned = list(conns), []

    def getconn(self):
        return self.free.pop(0) if self.free else _Conn()

    def putconn(self, conn, close=False):
        self.returned.append((conn, close))


@pytest.fixture(autouse=True)
def _fresh():
    db_pool._LAST_USED.clear()
    yield
    db_pool._LAST_USED.clear()


def test_a_dead_idle_connection_is_replaced_before_it_is_lent() -> None:
    dead = _Conn(dead=True)
    pool = _Pool(dead)
    with db_pool.borrowed(pool) as conn:
        assert conn is not dead and not conn.dead
    assert (dead, True) in pool.returned, "the dead one is closed, not kept"


def test_a_connection_that_breaks_while_lent_is_closed_not_kept() -> None:
    pool = _Pool(_Conn())
    with pytest.raises(psycopg2.OperationalError):
        with db_pool.borrowed(pool) as conn:
            conn.dead = True
            raise psycopg2.OperationalError("terminating connection due to administrator command")
    assert pool.returned[-1] == (conn, True)


def test_a_healthy_connection_goes_back_to_the_pool_and_is_not_checked_again_at_once() -> None:
    pool = _Pool(_Conn())
    with db_pool.borrowed(pool) as first:
        pass
    assert pool.returned[-1] == (first, False)
    pool.free.append(first)
    first.dead = True  # a check now would replace it; within the idle window none is made
    with db_pool.borrowed(pool) as again:
        first.dead = False
        assert again is first


def test_every_pooled_store_borrows_through_it() -> None:
    import inspect

    from app.server import auth, plugin_store, run_store

    assert "borrowed(self._pool)" in inspect.getsource(run_store.RunStore.get_connection)
    assert "borrowed(self._pool)" in inspect.getsource(plugin_store)
    assert "borrowed(_db_pool)" in inspect.getsource(auth.get_db_connection)
