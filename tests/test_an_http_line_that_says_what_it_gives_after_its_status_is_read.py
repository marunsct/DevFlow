"""An HTTP contract line that says what it gives after its status is read, with that text as its note.

Measured on one PHP run: five lines were written `AC-7 POST /notes -> 201 application/json` and `AC-9 GET /notes -> 200
ordered by id ASC`; each followed no form, so nothing checked them and the architect's review raised a major finding.
"""
from __future__ import annotations

from app.acceptance import interface_contract as ic


def test_a_content_type_after_the_status_is_a_note():
    checks, unread = ic.parse(["AC-7 POST /notes -> 201 application/json"])

    assert not unread and (checks[0].method, checks[0].path, checks[0].status) == ("POST", "/notes", 201)


def test_an_ordering_and_a_body_shape_after_the_status_are_notes():
    checks, unread = ic.parse(["AC-9 GET /notes -> 200 ordered by id ASC",
                               'AC-8 POST /notes -> 201 {"id": <integer>, "title": <string>}'])

    assert not unread and [c.status for c in checks] == [200, 201]


def test_a_second_status_after_or_is_still_a_status():
    checks, unread = ic.parse(["AC-4 POST /notes -> 400 or 422"])

    assert not unread and checks[0].statuses == (400, 422)
