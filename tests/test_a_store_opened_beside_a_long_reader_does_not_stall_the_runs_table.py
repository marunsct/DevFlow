"""A store opened while a long reader holds the runs table takes no lock that every later reader queues behind.

Measured on the live host: the nightly backup's dump read the tables for nine minutes; a process opened a run store
five minutes in, its schema check ran `ALTER TABLE runs ADD COLUMN IF NOT EXISTS ...` on a column that existed, the
ALTER waited for the dump's lock, and every read of `runs` queued behind the ALTER. Every web worker timed out, the
page answered nothing, and a deploy's pause step hung until the dump ended.
"""
from __future__ import annotations

import threading

import psycopg2

from app.server.run_store import RunStore, database_url


def test_a_current_schema_is_checked_without_a_lock_a_reader_waits_behind(setup_db):
    reader = psycopg2.connect(database_url())  # stands for the dump: a share lock on `runs`, held open
    reader.cursor().execute("SELECT 1 FROM runs LIMIT 1")
    opened: list[RunStore] = []
    opening = threading.Thread(target=lambda: opened.append(RunStore()), daemon=True)
    try:
        opening.start()
        opening.join(timeout=5)
        later = psycopg2.connect(database_url())
        try:
            cur = later.cursor()
            cur.execute("SET statement_timeout = '3s'")
            cur.execute("SELECT count(*) FROM runs")  # raises QueryCanceled if it queued behind a waiting ALTER
            assert cur.fetchone() is not None
        finally:
            later.close()
        assert not opening.is_alive(), "opening a store waited for the long reader"
    finally:
        reader.rollback()
        reader.close()
        opening.join(timeout=10)
        for store in opened:
            store.close()


def test_a_missing_column_is_still_added(setup_db):
    store = RunStore()
    try:
        with store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE runs DROP COLUMN IF EXISTS run_name")
            conn.commit()
        RunStore().close()
        with store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM information_schema.columns WHERE table_name = 'runs' AND column_name = 'run_name'")
                assert cur.fetchone() is not None
    finally:
        store.close()
