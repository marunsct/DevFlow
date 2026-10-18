"""A judgement model that could not be built is among the release's completion gaps (Initiative AH.3).

The run fell back to the build model for every review; that was a log line and
a run event, and the completion read as independently reviewed.
"""

from __future__ import annotations

import inspect

from app.graph import delivery
from app.models import roles


def test_a_downgrade_is_a_gap() -> None:
    token = roles._DOWNGRADE.set("The judgement model 'x' could not be built (ValueError)")
    try:
        assert delivery._reviews_that_were_not_independent() == [
            "The judgement model 'x' could not be built (ValueError)"
        ]
    finally:
        roles._DOWNGRADE.reset(token)


def test_no_downgrade_no_gap() -> None:
    assert delivery._reviews_that_were_not_independent() == []


def test_the_release_asks_for_it() -> None:
    assert "gaps.extend(_reviews_that_were_not_independent())" in inspect.getsource(delivery.release)
