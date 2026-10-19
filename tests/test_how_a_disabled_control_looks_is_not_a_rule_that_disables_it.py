"""How a disabled control looks is not advice to disable it (measured live).

The filter that drops "disable the control until the input is valid" also
dropped input styling advice: "a red border when invalid, and a light gray
background when disabled" has a disabling word and a condition on one line.
"""
from __future__ import annotations

from app.agents.specialist_advice import disables_on_a_condition


def test_styling_the_disabled_state_is_kept():
    styling = ("Form inputs show a 2px solid blue border on focus, a 1px solid red border with a red "
               "error message below when invalid, and a light gray background when disabled")
    assert not disables_on_a_condition(styling)
    assert not disables_on_a_condition("The disabled state uses 50% opacity, and inputs show a red border if empty.")


def test_disabling_on_a_condition_is_still_caught():
    for rule in (
        "The Add button is disabled until the title holds text.",
        "If invalid, the form disables the add control.",
        "Save is enabled only when the title is not empty.",
        "Disable the submit control while the request is in flight.",
    ):
        assert disables_on_a_condition(rule), rule
