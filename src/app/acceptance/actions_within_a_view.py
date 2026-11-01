"""QA tests an action taken while a view that depends on its result is on (behind `TESTS_OF_ACTIONS_WITHIN_A_VIEW`).

Measured on one run: two behaviours of a brief each had their tests, no locked test took the one while the other was
on, the suite was green, and the product left the wrong thing showing. A suite proves what QA thought to test, and
QA writes a criterion at a time, so the pair falls between two criteria. An older, always-on rule in QA's request asks
this of views that show records in some state, and that suite went without it all the same, so this wider rule may not
be enough either. It is a prompt rule: only a measured run's locked suite can show its effect, so it stays off until then.
"""

from __future__ import annotations

from app.switches import is_on

#: `TESTS_OF_ACTIONS_WITHIN_A_VIEW` set to on or off overrides this; off until measured.
ON_BY_DEFAULT = False
#: What the admin page says this switch does.
explanation = (
    "QA and the suite's review are told: where one action changes the state a current view depends on, a test takes the "
    "action while that view is on and checks what shows afterward."
)

AUTHOR_RULE = (
    "- Where one action changes the state a current view depends on - what is chosen, narrowed, ordered, counted or "
    "summed up - a test takes that action while that view is on, then checks what shows afterward, besides the tests of "
    "the action and of the view alone. Go through the criteria in pairs for these: each can pass alone while the two "
    "together leave the wrong thing showing.\n"
)
REVIEW_RULE = (
    "\n\nWhere one action changes the state a current view depends on, check that a test takes the action while that "
    "view is on and checks what shows afterward. Tests of the action and of the view apart pass a product that gets the "
    "two together wrong; name each such pair of criteria with no test of them together."
)


def enabled() -> bool:
    return is_on("TESTS_OF_ACTIONS_WITHIN_A_VIEW", ON_BY_DEFAULT)


def author_rule() -> str:
    """The line in QA's rules; "" when off."""
    return AUTHOR_RULE if enabled() else ""


def review_rule() -> str:
    """The closing line of the suite review's request; "" when off."""
    return REVIEW_RULE if enabled() else ""


__all__ = ["AUTHOR_RULE", "ON_BY_DEFAULT", "REVIEW_RULE", "author_rule", "enabled", "explanation", "review_rule"]
