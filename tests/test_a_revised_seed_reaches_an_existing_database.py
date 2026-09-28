"""A revised seed must reach a database that was already seeded - and never clobber an edit.

The seed was written with `ON CONFLICT DO NOTHING`. That protected an edited row,
and it also meant a revised seed never reached any database that had been seeded
before: the rows kept their first text for ever. Moving language- and
framework-specific guidance out of the agents' prompts and into this table is
only worth anything if the moved text actually arrives.

These run against the session's real Postgres, because the rule is SQL.
"""

from __future__ import annotations

import os
import uuid

import pytest

from app.plugins import seed as seed_module
from app.server.plugin_store import PluginStore


@pytest.fixture
def store(monkeypatch):
    return PluginStore(db_url=os.environ["DB_URL"])


def _row(store: PluginStore, name: str) -> tuple:
    with store.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT instructions, origin, seeded_instructions FROM plugin_instructions "
                "WHERE framework_name = %s",
                (name,),
            )
            return cur.fetchone()


def _set(store: PluginStore, name: str, **columns) -> None:
    assignments = ", ".join(f"{column} = %s" for column in columns)
    with store.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE plugin_instructions SET {assignments} WHERE framework_name = %s",
                (*columns.values(), name),
            )
        conn.commit()


def _reseed(monkeypatch, name: str, text: str) -> PluginStore:
    monkeypatch.setitem(seed_module.SEED_INSTRUCTIONS, name, text)
    return PluginStore(db_url=os.environ["DB_URL"])


@pytest.fixture
def name() -> str:
    return f"lang-{uuid.uuid4().hex[:8]}"


class TestTheSeed:
    def test_every_seed_row_is_written_and_marked(self, store) -> None:
        for framework, text in seed_module.SEED_INSTRUCTIONS.items():
            instructions, origin, seeded = _row(store, framework.lower())
            assert origin == "seed"
            assert seeded == instructions

    def test_a_revised_seed_refreshes_an_unedited_row(self, monkeypatch, name) -> None:
        store = _reseed(monkeypatch, name, "first version")

        store = _reseed(monkeypatch, name, "second version")

        assert _row(store, name)[0] == "second version"

    def test_a_hand_edited_row_is_never_overwritten(self, monkeypatch, name) -> None:
        store = _reseed(monkeypatch, name, "first version")
        _set(store, name, instructions="edited by an operator")

        store = _reseed(monkeypatch, name, "second version")

        assert _row(store, name)[0] == "edited by an operator"

    def test_a_generated_row_gives_way_to_a_curated_seed(self, monkeypatch, name, store) -> None:
        store.update_instructions(name, "a model's guess")
        assert _row(store, name)[1] == "generated"

        store = _reseed(monkeypatch, name, "curated guidance")

        assert _row(store, name)[:2] == ("curated guidance", "seed")

    def test_a_row_from_before_the_bookkeeping_is_refreshed(self, monkeypatch, name) -> None:
        store = _reseed(monkeypatch, name, "first version")
        _set(store, name, origin=None, seeded_instructions=None)

        store = _reseed(monkeypatch, name, "second version")

        assert _row(store, name)[0] == "second version"


class TestGeneratedRows:
    def test_generation_marks_its_row(self, store, name) -> None:
        store.update_instructions(name, "generated text")

        assert _row(store, name)[:2] == ("generated text", "generated")

    def test_generation_never_touches_a_seed_row(self, store) -> None:
        """The middleware only generates for names the store does not know."""
        assert "python" in store.get_all_framework_names()
