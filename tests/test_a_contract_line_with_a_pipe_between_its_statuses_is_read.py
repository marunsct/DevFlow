"""A contract line that separates its allowed statuses with a pipe is read like one that uses `or` or a slash.

Measured on a held-out run: `AC-10 GET /notes/{id} -> 200 | 404` and `AC-11 PUT /notes/{id} {...} -> 200 | 404` followed
none of the contract's forms, were set aside, and four lines went unchecked at release.
"""
from __future__ import annotations

from app.acceptance import interface_contract as contract


def test_a_pipe_separates_statuses_like_or():
    checks, set_aside = contract.parse(["AC-10 GET /notes/{id} -> 200 | 404"])
    assert set_aside == [] and checks[0].statuses == (200, 404) and checks[0].path == "/notes/{id}"


def test_a_pipe_after_a_body_is_read_too():
    line = 'AC-11 PUT /notes/{id} {"title": "string", "body": "string"} -> 200 | 404'
    checks, set_aside = contract.parse([line])
    assert set_aside == [] and checks[0].statuses == (200, 404)


def test_or_and_slash_are_still_read():
    checks, set_aside = contract.parse(["AC-1 POST /notes -> 201 or 400/422", "AC-2 GET /notes -> 200"])
    assert set_aside == [] and checks[0].statuses == (201, 400, 422) and checks[1].statuses == (200,)
