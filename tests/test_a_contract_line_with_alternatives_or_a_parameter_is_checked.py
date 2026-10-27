"""A contract line that allows several statuses, or names a route with a parameter, is checked at release.

Measured on several runs of one day: `AC-3 GET /notes/:id -> 200 or 404`, `AC-4 PUT /notes/{id} -> 200 or 400/422 or
404` and `AC-5 DELETE /notes/:id -> 204 or 404` were each listed as "follows none of the contract's three forms" or "a
route with a parameter in it" - the routes the product's main criteria use went unchecked at every release.
"""
from __future__ import annotations

from app.acceptance import interface_contract as contract


def test_alternatives_are_read_as_the_statuses_allowed():
    checks, unreadable = contract.parse([
        "AC-3 GET /notes/:id -> 200 or 404",
        "AC-4 PUT /notes/{id} -> 200 or 400/422 or 404",
        "AC-14 GET /health -> 200",
    ])

    assert unreadable == []
    assert [c.statuses for c in checks] == [(200, 404), (200, 400, 422, 404), (200,)]


def test_a_route_with_a_parameter_is_probed_with_a_record_that_does_not_exist_when_a_4xx_is_allowed():
    checks, _ = contract.parse(["AC-5 DELETE /notes/:id -> 204 or 404", "AC-3 GET /notes/:id -> 200"])

    probed = contract.checkable(checks)

    assert [c.path for c in probed] == ["/notes/" + contract.A_RECORD_THAT_DOES_NOT_EXIST]
    spec = contract.playwright_checks(probed)
    assert "[204,404]" in spec.replace(" ", "") and "toContain(answer.status())" in spec


def test_a_bare_write_is_checked_when_its_refusal_is_allowed():
    checks, _ = contract.parse(["AC-13 POST /notes -> 201 or 400/422", "AC-1 POST /notes -> 201"])

    assert [c.line for c in contract.checkable(checks)] == ["AC-13 POST /notes -> 201 or 400/422"]
