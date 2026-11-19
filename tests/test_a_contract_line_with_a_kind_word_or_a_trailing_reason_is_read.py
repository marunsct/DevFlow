"""A contract line that names its kind before the method, or says what it is for after its status, is read.

Measured on one hosted Rust run: the first specification wrote `AC-3 GET /notes/{id} -> 404 for an id no note has`;
told the line followed no form, the architect rewrote every line as `AC-1 route POST /notes -> 201`, after the review's
own examples (`page ...`, `command ...`). Sixteen lines, none read: the contract was empty, no probe asked a write, and
the product shipped accepting a title of spaces - a quality test lost.
"""
from __future__ import annotations

import pytest

from app.acceptance import interface_contract as ic


@pytest.mark.parametrize("line, method, path, statuses", [
    ("AC-1 route POST /notes -> 201", "POST", "/notes", (201,)),
    ("AC-3 route GET /notes/{id} -> 404", "GET", "/notes/{id}", (404,)),
    ("AC-7 endpoint PUT /notes/{id} -> 422", "PUT", "/notes/{id}", (422,)),
    ("AC-3 GET /notes/{id} -> 404 for an id no note has", "GET", "/notes/{id}", (404,)),
    ("AC-7 POST /notes -> 400 or 422 when the title is missing or empty", "POST", "/notes", (400, 422)),
])
def test_the_line_is_read_as_its_check(line, method, path, statuses):
    checks, unreadable = ic.parse([line])

    assert unreadable == []
    assert [(c.criterion, c.method, c.path, c.statuses) for c in checks] == [(line.split()[0], method, path, statuses)]


def test_a_trailing_reason_is_kept_as_the_line_s_note():
    checks, _ = ic.parse(["AC-3 GET /notes/{id} -> 404 for an id no note has"])

    assert "no note has" in checks[0].note


@pytest.mark.parametrize("line", [
    "AC-1 route POST notes -> 201",          # no path
    "AC-1 reroute POST /notes -> 201",       # not a kind word on its own
])
def test_a_line_that_still_follows_no_form_stays_unreadable(line):
    checks, unreadable = ic.parse([line])

    assert checks == [] and len(unreadable) == 1
