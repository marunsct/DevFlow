"""A bodiless write the product refuses for its missing content type is unchecked at release, like one refused for its body.

Measured on one run: `AC-4 PUT /notes/:id -> 200 | 404` was failed at release for the 415 a product gives the probe's
empty request with no content type, and a product at full hidden marks read as non-deliverable.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import interface_contract as ic


def _check(method="PUT"):
    return ic.Check(criterion="AC-4", kind="http", line=f"AC-4 {method} /notes/:id -> 200 | 404", method=method,
                    path="/notes/:id", status=200, statuses=[200, 404])


def test_a_415_on_a_bodiless_write_is_a_refusal_of_the_missing_body():
    test = SimpleNamespace(name="[AC-4] contract 3", message="Expected value: 415\nReceived array: [200, 404]")

    assert ic._a_bodiless_write_refused_first(_check(), test)


def test_a_read_answered_415_is_not():
    test = SimpleNamespace(name="[AC-2] contract 1", message="Expected value: 415\nReceived array: [200]")

    assert not ic._a_bodiless_write_refused_first(_check("GET"), test)
