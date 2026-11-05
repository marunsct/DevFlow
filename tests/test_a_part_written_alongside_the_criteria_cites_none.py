"""A part of the specification written alongside the criteria does not cite criterion ids it cannot see.

Measured on one run: the specification's parts are written at once, and the part holding `implementation_order`
cited AC ids while another part was writing the acceptance criteria and the interface contract; every step pointed
at the wrong criterion, and the first design review sent the whole specification back for it (blocking).
"""
import re
from types import SimpleNamespace

from app.graph import specification_parts as parts


def _spec():
    return SimpleNamespace(**{name: [] for name in parts.CORE})


def test_a_part_not_writing_the_criteria_is_told_to_cite_none():
    text = parts.part_request(_spec(), parts.PARTS[0], "")
    assert "AC-n" in text and "same time" in text


def test_the_part_writing_the_criteria_is_not():
    owner = next(p for p in parts.PARTS if "acceptance_criteria" in p)
    assert parts.CITE_NO_CRITERION not in parts.part_request(_spec(), owner, "")


def test_the_rule_avoids_the_banned_words():
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", parts.CITE_NO_CRITERION, re.I)
