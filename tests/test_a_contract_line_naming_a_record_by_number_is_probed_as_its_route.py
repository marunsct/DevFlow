"""A contract line naming a record by number is probed as the route it is an example of.

Measured over the scored runs: `AC-1 DELETE /api/bookmarks/1 -> 204` was probed at release as written, on a product
that held no record 1, and was reported twelve times as an interface contract the product does not keep.
"""
from __future__ import annotations

from app.acceptance import interface_contract
from app.acceptance.interface_contract import A_RECORD_THAT_DOES_NOT_EXIST, bad_body_checks, checkable, parse, with_a_record_made_first

LINES = [
    "AC-1 POST /api/bookmarks -> 201",
    "AC-1 DELETE /api/bookmarks/1 -> 204",
    "AC-2 GET /notes/999 -> 404",
    "AC-3 GET /api/v2/items -> 200",
    "AC-4 PUT /api/bookmarks/1 -> 200",
]


def _checks():
    return parse(LINES)[0]


def test_a_success_on_a_numbered_record_is_asked_of_one_made_first():
    made = {c.line: c for c in with_a_record_made_first(_checks(), [{"title": "t", "url": "https://x.example"}])}
    delete = made["AC-1 DELETE /api/bookmarks/1 -> 204"]
    assert delete.path == "/api/bookmarks/{id}" and delete.made_through == "/api/bookmarks"
    assert '"/api/bookmarks/" + encodeURIComponent(id)' in interface_contract._a_made_record_test("'t'", delete)


def test_a_refusal_on_a_numbered_record_is_asked_of_one_that_does_not_exist():
    asked = {c.line: c for c in checkable(_checks())}
    assert asked["AC-2 GET /notes/999 -> 404"].path == f"/notes/{A_RECORD_THAT_DOES_NOT_EXIST}"
    assert "AC-1 DELETE /api/bookmarks/1 -> 204" not in asked  # no bare probe of a record that is not there
    assert asked["AC-3 GET /api/v2/items -> 200"].path == "/api/v2/items"


def test_a_bad_body_on_a_numbered_record_reaches_one_made_first():
    asked, unchecked = bad_body_checks(_checks(), [])
    [put] = [c for c in asked if c.method == "PUT"]
    assert put.path == "/api/bookmarks/{id}" and put.made_through == "/api/bookmarks"


def test_two_numbers_in_a_route_are_left_as_written():
    [check] = parse(["AC-5 GET /lists/1/items/2 -> 200"])[0]
    assert interface_contract._a_literal_id_as_a_parameter(check).path == "/lists/1/items/2"
