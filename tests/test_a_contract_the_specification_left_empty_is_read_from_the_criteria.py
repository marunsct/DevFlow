"""A contract the specification left empty is read from criteria that state a route and its answer (found on a run).

Measured on one run: the specification's interface contract was "Not specified"; the criteria said each route and its
answer; every release probe considered nothing, so the writes behind sign-in, the concurrent create and the emptied
title went unprobed.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import interface_contract as ic

CRITERIA = [
    SimpleNamespace(id="AC-9", text='POST /signup with {"username": ..., "password": ...} answers 201 with '
                                    '{"username": ...}, or 409 when the username is taken.'),
    SimpleNamespace(id="AC-10", text='POST /signin with {"username": ..., "password": ...} answers 200 with '
                                     '{"token": <string>}, or 401 when they do not match an account'),
    SimpleNamespace(id="AC-12", text='POST /items with {"title": ...} answers 201 with the item. A missing or empty '
                                     'title is refused with 400 or 422, and nothing is stored'),
    SimpleNamespace(id="AC-13", text="GET /items answers 200 with a JSON array of the signed-in person's items only"),
    SimpleNamespace(id="AC-14", text='PATCH /items/{id} with {"done": true|false} answers 200 with the item, or 404'),
    SimpleNamespace(id="AC-15", text="DELETE /items/{id} answers 204, or 404 when it is not one of the person's items"),
    SimpleNamespace(id="AC-1", text="A person can keep a private list of items"),
]


def test_each_route_a_criterion_states_becomes_a_contract_line():
    assert ic.lines_from_the_criteria(CRITERIA) == [
        "AC-9 POST /signup -> 201", "AC-10 POST /signin -> 200", "AC-12 POST /items -> 201",
        "AC-13 GET /items -> 200", "AC-14 PATCH /items/{id} -> 200", "AC-15 DELETE /items/{id} -> 204",
    ]


def test_the_lines_read_are_ones_the_contract_parses():
    checks, unreadable = ic.parse(ic.lines_from_the_criteria(CRITERIA))
    assert unreadable == [] and len(checks) == 6
    assert {(c.method, c.path, c.status) for c in checks} >= {("POST", "/items", 201), ("DELETE", "/items/{id}", 204)}


def test_the_lock_keeps_them_when_the_specification_gave_none(tmp_path, monkeypatch):
    from app.acceptance import suite

    monkeypatch.setattr(suite, "criteria", lambda root: CRITERIA)
    saved = {}
    monkeypatch.setattr(suite, "_state", lambda root: {})
    monkeypatch.setattr(suite, "_save_state", lambda root, state: saved.update(state))

    kept = ic.record_at_lock(tmp_path, (), specification=None)

    assert len(kept) == 6 and len(saved["interface_contract"]) == 6


def test_a_criterion_with_no_route_gives_no_line():
    assert ic.lines_from_the_criteria([CRITERIA[-1]]) == []


def test_a_lock_that_kept_no_lines_reads_them_from_the_criteria_at_release(tmp_path, monkeypatch):
    from app.acceptance import suite

    monkeypatch.setattr(suite, "criteria", lambda root: CRITERIA)
    monkeypatch.setattr(suite, "_state", lambda root: {"interface_contract": []})

    assert len(ic.the_locked_contract(tmp_path)) == 6
