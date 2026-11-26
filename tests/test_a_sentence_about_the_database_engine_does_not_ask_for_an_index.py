"""A specification's sentence about what the database engine does is not a request for an index.

Measured on a scored run: its specification said "SQLite provides ACID transactions ensuring crash safety (a write
either fully commits or fully rolls back), indexed lookups for O(log n) access", the quality check read "indexed" as
the specification asking for an index, found none declared, and the product's quality fell from 1.0 to 0.75.
"""
from __future__ import annotations

from app.analysis.product_quality import _ASKS_FOR_AN_INDEX, _asks_for

ENGINE = ("SQLite provides ACID transactions ensuring crash safety (a write either fully commits or fully rolls back), "
          "indexed lookups for O(log n) access, and a single file under DATA_DIR.")


def test_a_sentence_about_the_engine_asks_for_no_index() -> None:
    assert _asks_for(ENGINE, _ASKS_FOR_AN_INDEX) == []


def test_a_specification_that_names_what_to_index_still_asks() -> None:
    for asked in ("Add an index on owner_id for the list query.",
                  "Notes are indexed by owner so a user's list is fast.",
                  "Create indexes on created_at and done."):
        assert _asks_for(asked, _ASKS_FOR_AN_INDEX), asked
