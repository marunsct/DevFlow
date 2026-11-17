"""One statement that denies a subject is one open point, however many statements mention that subject.

Measured over four runs: 7 denials ("DELETE /notes/{id} -> 204 with no response body") were named 43 times as
"says opposite things", once against each endpoint that has a body, and filled the gate's cap of 12 in three runs.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.graph import one_design_review


class _Spec(BaseModel):
    api_and_event_contracts: list[str] = []
    test_cases: list[str] = []


def test_a_denial_against_three_statements_is_named_once():
    found = one_design_review.contradictions(_Spec(
        api_and_event_contracts=["DELETE /notes/{id} -> 204 with no response body"],
        test_cases=["POST /notes -> 201; the response body holds the note",
                    "GET /notes -> 200; the response body is an array",
                    "GET /notes/{id} -> 200; the response body is the note"],
    ))

    assert len(found) == 1 and "response body" in found[0]


def test_two_denials_are_two_points():
    found = one_design_review.contradictions(_Spec(
        api_and_event_contracts=["DELETE /notes/{id} -> 204 with no response body", "No graceful shutdown"],
        test_cases=["GET /notes -> 200; the response body is an array", "Graceful shutdown on SIGTERM closes the server"],
    ))

    assert len(found) == 2
