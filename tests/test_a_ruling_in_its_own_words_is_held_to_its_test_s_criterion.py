"""A ruling that calls a test wrong in its own words is taken with the test's own criterion quoted, behind a switch.

Measured on two runs: five rulings rightly called a test wrong - 24 characters for a 25-character string - each
quoting the criterion in its own words ("count_characters returns len(text)"); each was refused and the runs went on
fixing products that counted right. The repair is held to the criterion the harness holds, never to the judge's text.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.agents import suite_dispute as sd

STANDARD = "- AC-7 characters counts every character, newlines included.\n"
CRITERION = "AC-7 characters counts every character, newlines included"
TEST = "test_ac1_ac6_ac7_basic_file"


def _answer():
    return SimpleNamespace(rulings=[SimpleNamespace(
        test=TEST, the_test_is_wrong=True,
        the_test_asserts="the character count of 'Hello world foo bar baz \\n' is 24",
        the_standard_says="count_characters returns len(text), which for that string is 25, not 24.")])


def _named(monkeypatch, on: bool, criteria_of):
    monkeypatch.setenv("DISPUTE_QUOTES_THE_CRITERION", "on" if on else "off")
    monkeypatch.setattr(sd.structured_verdict_switch, "enabled", lambda: True)
    refused: list = []
    named = sd.tests_it_names(_answer(), [TEST], standard=STANDARD, refused=refused, criteria_of=criteria_of)
    return named, refused


def test_on_the_test_s_own_criterion_is_quoted_and_the_judge_s_words_labelled(monkeypatch):
    named, refused = _named(monkeypatch, True, {TEST: CRITERION})
    assert refused == [] and len(named) == 1
    assert f'Its criterion says "{CRITERION}"' in named[0]
    assert "(the judge's reading: count_characters returns len(text)" in named[0]


def test_off_it_is_refused_as_before(monkeypatch):
    named, refused = _named(monkeypatch, False, {TEST: CRITERION})
    assert named == [] and refused == [(TEST, "quotes what the standard does not say")]


def test_without_the_test_s_criterion_it_is_still_refused(monkeypatch):
    named, refused = _named(monkeypatch, True, {})
    assert named == [] and refused


def test_the_switch_is_off_in_its_code_and_built_in():
    """Built in since 11-13 (four right rulings refused on two runs); its code default stays off, as every switch's."""
    from app import switches

    assert sd.CRITERION_QUOTED_ON_BY_DEFAULT is False
    assert "DISPUTE_QUOTES_THE_CRITERION" in switches.BUILT_IN
