"""Many tests answered the same wrong status are read as one cause from a Playwright `toBe`, as from a pytest assert.

Measured on a Rust run: 14 of 19 failing Playwright tests answered 500 on every route ("Expected: 201 / Received: 500");
none was read as one cause, and nine fixers each chased it, one criterion at a time.
"""
from __future__ import annotations

from app.graph.acceptance_nodes import one_refusal_for_all


def _playwright(expected: int, received: int) -> str:
    return (f"crud.spec.js:12:1 › creates a note\n\n    Error: expect(received).toBe(expected) // Object.is equality\n\n"
            f"    Expected: {expected}\n    Received: {received}\n")


def _criteria(*answers):
    return [{"id": f"AC-{n}", "tests": [{"name": f"[AC-{n}] t", "outcome": "failed", "message": _playwright(e, r)}]}
            for n, (e, r) in enumerate(answers, start=1)]


def test_every_route_answering_500_is_one_cause():
    assert one_refusal_for_all(_criteria((201, 500), (200, 500), (204, 500), (200, 500))) == ("500", 4)


def test_different_wrong_answers_are_their_own_causes():
    assert one_refusal_for_all(_criteria((201, 500), (200, 404), (204, 422))) is None
