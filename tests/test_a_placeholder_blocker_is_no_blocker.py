"""A fix stage that answered `"blockers": ["None"]` was read as blocked.

One run's fix stage, sent a defect an earlier stage had already fixed, changed
nothing and said so - with `"blockers": ["None"]`. A stage that is blocked and
changed nothing leaves its defect open, so the ledger recorded a fixed defect as
"left open - the fix stage changed nothing and reported: None".
"""

from __future__ import annotations

import pytest

from app.agents.specialists import SpecialistOutput


@pytest.mark.parametrize("placeholder", ["None", "none.", "N/A", " n/a ", "-", "No blockers", "Not applicable", ""])
def test_a_placeholder_is_dropped(placeholder: str) -> None:
    assert SpecialistOutput(decisions=["already fixed"], blockers=[placeholder]).blockers == []


def test_a_real_blocker_is_kept() -> None:
    answer = SpecialistOutput(blockers=["None", "The locked test looks for a label the brief never names"])

    assert answer.blockers == ["The locked test looks for a label the brief never names"]


def test_a_blocker_that_mentions_none_is_kept() -> None:
    assert SpecialistOutput(blockers=["None of the fixtures load"]).blockers == ["None of the fixtures load"]
