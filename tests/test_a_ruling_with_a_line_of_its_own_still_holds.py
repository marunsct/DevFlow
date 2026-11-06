"""A dispute ruling whose quoted standard is mostly the standard's own words, with a line of the judge's own, holds.

Measured on one run: three rulings in a row rightly called a test wrong - it expects `done=True` for an item it never
marked done - quoting "AC-3: Create an item with a title; it starts not done. POST /items with {"title": ...} answers
201 with the item." and adding "The spec's ItemCreate request body has only a title field - no done parameter." Each
sentence had to be found in the standard, so the judge's own summary line refused every ruling and the sprint was
planned again three times. A quote made up mostly of what the standard does not say is still refused.
"""
from app.agents import suite_dispute as sd

STANDARD = ("- AC-3 Create an item with a title; it starts not done\n"
            "POST /items with {\"title\": ...} answers 201 with the item, or 400 when the title is empty.\n")


def test_two_lines_of_the_standard_and_one_summary_hold():
    quoted = ("AC-3: Create an item with a title; it starts not done. POST /items with {\"title\": ...} answers 201 "
              "with the item. The spec's ItemCreate request body has only a title field - no done parameter.")
    assert sd._the_standard_holds(quoted, STANDARD)


def test_a_quote_mostly_not_in_the_standard_is_refused():
    quoted = ("Every test must be independent and never rely on restarts or ordering of any kind. "
              "Items keep their done status only when marked through the update route on every single call. AC-3.")
    assert not sd._the_standard_holds(quoted, STANDARD)


def test_a_sentence_of_the_instructions_alone_is_refused():
    assert not sd._the_standard_holds("Name a test only when it could not pass for any product that does it.", STANDARD)


FILTER_STANDARD = '- A text field labelled "Filter by tag" shows only the bookmarks with exactly that tag; when it is empty, all are shown\n'


def test_a_short_quote_with_a_gloss_after_a_dash_holds():
    """Measured on one run: `"when it is empty, all are shown" - meaning every bookmark in the database` was refused:
    one sentence of 12 words, needing 8 of them in a row in the standard, though its quoted half was verbatim."""
    assert sd._the_standard_holds('"when it is empty, all are shown" — meaning every bookmark', FILTER_STANDARD)


def test_a_gloss_longer_than_its_quote_is_refused():
    assert not sd._the_standard_holds(
        '"all are shown" — meaning every record ever stored by any user of any service anywhere in the world',
        FILTER_STANDARD)
