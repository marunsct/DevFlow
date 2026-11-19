"""A product on SQLite is told how its connections are opened, closed and shared, whatever language it is written in.

Measured on two runs of one day: a Python service opened a connection per request and never closed it, so the locked
suite's sequence queued on "database is locked" and timed out (eleven fixes across two sprints); a C# service lost
writes when sixteen notes were created at once (three fixes, the quality test lost). Neither stack had any SQLite
guidance: the seed has PostgreSQL's and no other database's.
"""
from __future__ import annotations

import re

from app.plugins.seed import SEED_INSTRUCTIONS

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_sqlite_has_its_own_guidance():
    guidance = SEED_INSTRUCTIONS["sqlite"]

    assert "busy timeout" in guidance.lower() and "wal" in guidance.lower()
    assert "close" in guidance.lower()
    assert "max(id)" in guidance.lower()


def test_it_names_no_product_and_no_language_of_its_own():
    guidance = SEED_INSTRUCTIONS["sqlite"]

    assert not BANNED.search(guidance)
    assert not re.search(r"\b(?:python|fastapi|c#|asp\.net|rust|axum|go|java)\b", guidance, re.I)
