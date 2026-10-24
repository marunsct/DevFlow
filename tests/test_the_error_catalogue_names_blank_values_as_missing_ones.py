"""The specification's error catalogue treats an empty or whitespace-only required value as a missing one.

Measured over several runs: the one quality test the products kept failing was "a title of only spaces is refused and
nothing is stored" - the product answered 201 - and no rule anywhere named the blank-value case.
"""
from __future__ import annotations

import re

from app.agents.principal_architect import TechnicalSpecificationOutput

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _description() -> str:
    return TechnicalSpecificationOutput.model_fields["error_catalogue"].description or ""


def test_the_catalogue_is_told_a_blank_value_is_a_missing_one():
    text = _description()

    assert "empty or only whitespace once trimmed" in text and "exactly as when it is missing" in text


def test_the_description_uses_none_of_the_banned_words():
    assert not BANNED.search(_description())
