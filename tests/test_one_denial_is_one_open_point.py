"""One statement that denies a subject is one open point, however many statements mention that subject.

Measured over four runs: 7 denials were named 43 times as "says opposite things", once against each statement that
mentions their subject, and filled the gate's cap of 12 in three runs.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.graph import one_design_review


class _Spec(BaseModel):
    reliability_and_observability: list[str] = []
    deployment: list[str] = []


def test_a_denial_against_three_statements_is_named_once():
    found = one_design_review.contradictions(_Spec(
        reliability_and_observability=["No graceful shutdown: the process exits at once."],
        deployment=["Graceful shutdown on SIGTERM closes the server",
                    "Graceful shutdown waits for requests in flight",
                    "Graceful shutdown is logged at INFO"],
    ))

    assert len(found) == 1 and "graceful shutdown" in found[0]


def test_two_denials_are_two_points():
    found = one_design_review.contradictions(_Spec(
        reliability_and_observability=["No graceful shutdown: the process exits at once.",
                                       "No rate limiting or request throttling is implemented."],
        deployment=["Graceful shutdown on SIGTERM closes the server",
                    "Rate limiting: 5 requests per minute per IP on /auth/login."],
    ))

    assert len(found) == 2
