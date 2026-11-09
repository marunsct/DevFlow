"""A ruling on a specification contradiction is kept when its quotes are the specification's sentences, marks aside.

Measured on one run: a right ruling quoted `get_current_user(token: str = Header(...))` without the specification's
backticks, the word-for-word check rejected it, and the contradiction stayed open. The same fault was fixed for the
suite dispute as LF.543; this is that matcher applied here.
"""
from __future__ import annotations

from app.agents.specification_rulings import Ruling, Rulings, verified

SPEC = (
    "## Errors\n\nMissing Authorization header on any authenticated endpoint returns HTTP 401 with body "
    "{\"error\": \"Not authenticated\"}; no database state is modified.\n\n## Functions\n\n"
    "`get_current_user(token: str = Header(...))` parses the Authorization header, strips the `Bearer ` prefix, "
    "resolves tokens via `db.resolve_token()`, and raises HTTPException(401) for missing or invalid tokens.\n"
)
FIRST = "Missing Authorization header on any authenticated endpoint returns HTTP 401 with body {\"error\": \"Not authenticated\"}; no database state is modified."
SECOND = "get_current_user(token: str = Header(...)) parses the Authorization header, strips the Bearer prefix, resolves tokens via db.resolve_token(), and raises HTTPException(401) for missing or invalid tokens."


def _ruling(second: str) -> Rulings:
    return Rulings(rulings=[Ruling(finding=1, first_statement=FIRST, second_statement=second, stands="first", why="the brief says so")])


def test_a_quote_without_the_specification_s_marks_is_kept():
    assert len(verified(_ruling(SECOND), SPEC, ["finding one"])) == 1


def test_a_quote_the_specification_does_not_hold_is_still_rejected():
    made_up = "get_current_user returns the user's full profile and a fresh token on every call, without checking anything."
    assert verified(_ruling(made_up), SPEC, ["finding one"]) == []
