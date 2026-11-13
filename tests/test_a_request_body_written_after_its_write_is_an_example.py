"""A JSON body written right after the write that sends it is a request example, whatever section of the
specification holds it, and comes before the shapes of answers.

Measured on one run: the contracts held only error bodies (`{"detail": "Title is required"}`), the request bodies
stood in the test cases (`PUT /notes/{id} with {"title": ...}`), the emptied-field probe found no title to empty, the
product accepted an update that emptied the title, and a hidden test failed while the locked suite passed.
"""
from types import SimpleNamespace

from app.acceptance import interface_contract as ic

SPEC = SimpleNamespace(
    data_contracts=['Error response body: {"detail": "Title is required"}'],
    api_and_event_contracts=['A missing note answers 404 with {"detail": "Note not found"}'],
    test_cases=['- AC-4: Setup: POST /notes {"title": "Old", "body": "old"}, extract id. Steps: PUT /notes/{id} with '
                '{"title": "Updated Title", "body": "Updated body"}. Assertions: status_code is 200.'],
    function_contracts=[],
)
LINES = ["- AC-1 POST /notes -> 201", "- AC-4 PUT /notes/{id} -> 200", "- AC-5 DELETE /notes/{id} -> 204"]


def test_the_bodies_sent_by_writes_come_first():
    bodies = ic.example_bodies(SPEC)
    assert bodies[0] == {"title": "Old", "body": "old"}
    assert {"title": "Updated Title", "body": "Updated body"} in bodies
    assert bodies.index({"detail": "Title is required"}) > 1


def test_with_them_every_write_is_probed_with_the_title_emptied():
    checks, _ = ic.parse(LINES)
    fields = ic.fields_refused_when_empty(["A title that is missing or empty is refused with 400 or 422"])
    asked, _ = ic.emptied_field_checks(checks, ic.example_bodies(SPEC), fields)
    assert {(c.method, c.emptied) for c in asked} >= {("POST", "title"), ("PUT", "title")}
