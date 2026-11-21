"""A create line whose writes made at once were answered 500 carries the error the server printed for them.

Measured on one run: sixteen creates at once answered 500, the defect showed only the statuses, and four fixes in a
row guessed at a locked database while the service had printed the real cause (a table it never created).
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import concurrent_write_probe as probe

PRINTED = ("INFO: 127.0.0.1 - \"POST /items HTTP/1.1\" 500 Internal Server Error\n"
           "sqlite3.OperationalError: no such table: accounts\n")


def _errors():
    check = SimpleNamespace(method="POST", path="/items", line="POST /items -> 201")
    return [(check, {"statuses": [500] * 16, "sent": 16, "body": {"title": "Buy milk"}})]


def test_the_server_s_error_is_in_what_the_defect_says():
    (check, found), = probe.with_what_the_server_printed(_errors(), PRINTED)

    said = probe.what_came_back(found)

    assert "no such table: accounts" in said and "the server printed:" in said


def test_a_create_line_the_server_answered_well_is_given_nothing():
    errors = [(c, {**f, "statuses": [201] * 16}) for c, f in _errors()]

    (_, found), = probe.with_what_the_server_printed(errors, PRINTED)

    assert "printed" not in found
