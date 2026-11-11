"""An open question answered "-> Assumption: ..." is recorded with that answer, not the generic one.

Measured on one run: all five intake assumptions were written "-> Assumption:", none was split, and each decision
was recorded as "The simplest reading that meets the brief; nothing beyond it."
"""
from __future__ import annotations

from app.agents.assumptions import SIMPLEST, assumed


def test_each_way_of_writing_it_is_split():
    pairs = assumed([
        "How should items be ordered? -> Assumption: newest first",
        "Is a description required? -> assumed: no",
        "Confirm before deleting? → Assume: no confirmation",
        "Which colour for done items?",
    ])
    assert pairs == [
        ("How should items be ordered?", "newest first"),
        ("Is a description required?", "no"),
        ("Confirm before deleting?", "no confirmation"),
        ("Which colour for done items?", SIMPLEST),
    ]
