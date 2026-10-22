"""Every place that states a capability must state the same one.

Playwright became mandatory for frontend UI code on 2026-09-17, and the
Dockerfile gained Chromium's system libraries for it. Two older mechanisms
were never told, and on 2026-09-19 the harness held three incompatible
positions at once:

    testability.py            "YOU MUST USE Playwright"
    stack_selector.py         "There is NO browser and no display"
    tools_models.py           rejected "headless browser testing with Playwright"
    ROLE_EXECUTABLES          `playwright` on no role's allowlist

So the stage that chooses the testing approach was told a browser could not
exist; if it chose one anyway and phrased it the natural way, the validator
threw the whole answer away; and the specialist downstream was ordered to use
one regardless. One run spent six refusals and part of seven sprint
cycles inside that contradiction.

This is root-cause class A in its most expensive form: one fact, four copies,
and a capability added to one of them. These tests make the copies agree by
derivation, so adding or removing a capability fails here rather than in a run.
"""

from __future__ import annotations

import pytest

from app.agents.stack_selector import EXECUTION_ENVIRONMENT
from app.agents.testability import TESTABILITY_RULE
from app.agents.tools_models import TechnologyStack
from app.tools.sandbox import ROLE_EXECUTABLES, allowed_executables


def _a_browser_is_runnable() -> bool:
    return any("playwright" in names for names in ROLE_EXECUTABLES.values())


def test_a_mandated_runner_is_on_the_allowlist_of_the_roles_told_to_use_it():
    """If guidance orders a tool, the roles it orders must be able to run it.

    The order moved from the testability rule to the seed row of the stacks
    that render a page, so that is where it is looked for. It must not quietly
    skip when the wording moves: a mandate nobody can obey is the defect this
    file exists to catch.
    """
    from app.plugins.seed import SEED_INSTRUCTIONS

    mandating = [name for name, text in SEED_INSTRUCTIONS.items() if "with Playwright" in text]
    assert mandating, "no stack's guidance orders Playwright any more; revisit this file"
    for role in ("ui_ux_specialist", "testing_specialist"):
        assert "playwright" in allowed_executables(role), (
            f"{role} is told Playwright is mandatory and cannot name it. "
            "`npx playwright` works only because npx runs anything."
        )


def test_no_prompt_denies_a_capability_the_harness_provides():
    """The stack selector may not tell the deciding stage a browser cannot exist."""
    if not _a_browser_is_runnable():
        pytest.skip("no browser is available, so denying one is correct")
    denials = [
        line
        for line in EXECUTION_ENVIRONMENT.splitlines()
        if "NO browser" in line or "no browser" in line
    ]
    assert not denials, (
        "the stack selector is told a browser is impossible while the harness "
        f"provides one: {denials}"
    )


def test_the_prompt_still_denies_what_is_genuinely_impossible():
    """The true half must survive the fix: no display, no human, no manual check."""
    text = EXECUTION_ENVIRONMENT.lower()
    assert "no display" in text, "a headless browser is still not a person watching"
    assert "manual browser testing" in text, "manual checks are still impossible"


@pytest.mark.parametrize(
    "value",
    ["Playwright", "headless browser testing with Playwright",
     "Playwright (Chromium, headless)", "node --test", "pytest", "go test"],
)
def test_a_runnable_testing_approach_is_accepted(value):
    """A named runner the sandbox can execute settles it, whatever words surround it."""
    TechnologyStack(
        language="TypeScript", framework="React", database="none",
        testing_framework=value,
    )


@pytest.mark.parametrize(
    "value",
    ["Manual browser testing", "Visual inspection in DevTools",
     "None", "manual testing by hand"],
)
def test_an_unrunnable_testing_approach_is_still_refused(value):
    with pytest.raises(Exception):
        TechnologyStack(
            language="TypeScript", framework="React", database="none",
            testing_framework=value,
        )


def test_the_validator_derives_its_runners_rather_than_listing_them():
    """The mechanism, not just today's outcome.

    `_must_be_runnable` recognises a runner by looking it up in the allowlist.
    That is what makes it correct as capabilities change - and it is why
    Playwright being absent from every allowlist silently broke it.
    """
    import inspect

    from app.agents import tools_models

    source = inspect.getsource(tools_models.TechnologyStack._must_be_runnable.__func__)
    assert "ROLE_EXECUTABLES" in source, (
        "the validator must derive its runners from the allowlist, not from a "
        "hard-coded list that drifts from what the sandbox can run"
    )
