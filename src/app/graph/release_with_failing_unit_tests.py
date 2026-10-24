"""A product the locked suite accepts is released with its failing unit tests recorded, not held back until the run stops (behind `RELEASE_WITH_FAILING_UNIT_TESTS`).

Measured on a small-model run: the acceptance suite passed every criterion but one a dispute had already
deferred, and the hidden tests passed 9 of 9, yet the run ended as failed. The only thing failing was the
project's own unit tests, which the same model had written and could not make pass: each fixer gave up or was
reverted for breaking a test that passed. The release gate held the product back for them, each hold sent the last
sprint round again, each round ended in an escalation, and the escalation budget ran out ("not converging").

The unit tests do ship with the product, so a failure is not hidden: it becomes a gap in the run's record
(`completion_gaps`), named with the tests, like a deferred criterion. It is released this way only when
the only thing failing is the project's own unit tests - never when a criterion fails, the suite does not run, or
the handoff is not ready - and when the harness has already given those tests its chances: the sprint was accepted
at an escalation with them open, or the release has already held the product back as often as it may.
"""
from __future__ import annotations

from collections.abc import Sequence

from app.switches import is_on

#: Off in code like every switch; the compose file turns it on (the owner's baseline rule).
ON_BY_DEFAULT = False


def enabled() -> bool:
    return is_on("RELEASE_WITH_FAILING_UNIT_TESTS", ON_BY_DEFAULT)


def may_ship(
    unit_failures: Sequence[str], failing: Sequence[str], *, accepted_at_an_escalation: bool,
    release_attempts: int, most_release_attempts: int,
) -> bool:
    """Whether the release goes ahead although the project's own unit tests fail."""
    if not enabled() or not unit_failures or list(failing) != list(unit_failures):
        return False
    return accepted_at_an_escalation or release_attempts >= most_release_attempts


def gap(unit_failures: Sequence[str]) -> str:
    named = "; ".join(str(name) for name in unit_failures[:6])
    more = f" and {len(unit_failures) - 6} more" if len(unit_failures) > 6 else ""
    return (
        f"{len(unit_failures)} of the project's own unit tests still fail and ship failing (the locked acceptance "
        f"suite passes; the fixes did not close them): {named}{more}."
    )
