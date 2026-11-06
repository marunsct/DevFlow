"""A ruling quoting a criterion verbatim, then a dash and its own reason, quotes the standard.

Measured on one run: two right rulings (each test created two records and asserted three) quoted the criterion
"Filter tasks by status (all, active, completed)" and went on after a dash with why the test is wrong; the gloss was
longer than the quote, the guard counted it against the quote, and both tests stayed locked - the run re-planned a
product that met its criteria.
"""
from __future__ import annotations

from app.agents.suite_dispute import _the_standard_holds

STANDARD = (
    "AC-5: Filter tasks by status (all, active, completed)\n"
    "AC-15: Filter functionality works correctly\n"
    "AC-7: A task cannot be added without a title\n"
)


def test_a_verbatim_criterion_then_a_long_gloss_holds():
    quoted = ("Filter tasks by status (all, active, completed) — the test creates only two tasks total but asserts "
              "a count of three under All, which its own steps never set up")
    assert _the_standard_holds(quoted, STANDARD)


def test_a_short_verbatim_lead_does_not_carry_an_invented_sentence():
    assert not _the_standard_holds("Filter functionality - every filter keeps a count badge beside its name", STANDARD)


def test_an_invented_standard_still_refuses():
    assert not _the_standard_holds("Each filter shows a count of the records it holds beside its label", STANDARD)
