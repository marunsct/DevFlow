"""A criterion that only restates the others is neither raised as failing nor shipped as a cut.

Measured on three runs (PHP 8, Go 11, C# 14): "Every operation works as the interface says" and "all above criteria pass"
had no test of their own, were raised as failing or deferred, and lowered the verdict to "delivered with cuts".
"""
from __future__ import annotations

import pytest

from app.acceptance import criteria

AGGREGATES = [
    "Every operation works as the interface says",
    "all above criteria pass",
    "All requirements are met and every operation works",
]
REAL = [
    "Every request without a token answers 401",
    "A title that is missing or empty is refused with 400 or 422",
    "Users can add, edit and delete notes",
    "Each note has an id that never changes",
]


@pytest.mark.parametrize("text", AGGREGATES)
def test_an_aggregate_is_recognised(text):
    assert criteria.is_an_aggregate(text)


@pytest.mark.parametrize("text", REAL)
def test_a_real_criterion_is_not_taken_for_one(text):
    assert not criteria.is_an_aggregate(text)
