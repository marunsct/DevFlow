"""Per-sprint test and bug-remediation loop (Step 5.4).

The workflow plan requires every sprint to run a test-then-fix loop before it
can be accepted: implement a small increment, run tests, track any failure as
an owned defect, route it to a specialist, fix it, add a regression test, and
rerun. This module models that loop as pure, typed state transitions (like
`app.review`) instead of a live agent, because the loop itself is
deterministic bookkeeping — deciding *whether* a sprint may be accepted — while
the actual fixing is done by specialist Deep Agents (Step 5.3).

A sprint must not loop forever on a defect that never gets fixed, so every
remediation cycle has a bounded number of attempts; exceeding it raises
`RemediationLimitExceeded` instead of retrying silently.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_MAX_REMEDIATION_ATTEMPTS = 3
"""Bound the number of test-fix-retest cycles per sprint before escalating."""


class RemediationLimitExceeded(RuntimeError):
    """Raised when a sprint's remediation loop would exceed its attempt limit."""


DefectStatus = Literal["open", "fixed", "accepted_risk"]


class Defect(BaseModel):
    """One tracked test failure, with everything needed to route and verify a fix."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(..., description="Short summary of what is wrong.")
    severity: str = Field(..., description="Impact level, e.g. 'blocking', 'major', 'minor'.")
    reproduction_steps: str = Field(..., description="How to reliably reproduce the failure.")
    expected_behavior: str = Field(..., description="What should have happened.")
    actual_behavior: str = Field(..., description="What actually happened.")
    affected_files: list[str] = Field(default_factory=list)
    owner: str = Field(..., description="Specialist role or person responsible for the fix.")
    regression_test_required: bool = Field(
        default=True, description="Whether a new regression test is required before this defect can be closed."
    )
    regression_test: str | None = Field(
        default=None, description="The regression test added for this defect, once fixed."
    )
    caught_by: str = Field(
        default="",
        description=(
            "The test command that was already failing when this defect was reported, "
            "or ''. A defect a test already catches needs no new test: that command "
            "passing is its proof. Set by the controller, never by a specialist."
        ),
    )
    source: str = Field(
        default="",
        description="Which check raised it. Set by the controller, never by a specialist.",
    )
    failing_criteria: list[str] = Field(
        default_factory=list,
        description=(
            "The acceptance criteria this defect names that the harness's own run of "
            "the locked suite found failing when it was reported. Set by the "
            "controller, never by a specialist."
        ),
    )
    status: DefectStatus = Field(default="open")
    fix_attempts: int = Field(
        default=0, ge=0,
        description="Fix stages that ran on this defect and left it open, or were reverted.",
    )
    verified_by: str = Field(
        default="",
        description=(
            "The command the execution ledger confirms ran and exited 0 for this "
            "fix, or '' when nothing was recorded. Set by the controller, never "
            "by a specialist."
        ),
    )
    accepted_risk_reason: str | None = Field(
        default=None, description="Why this defect was accepted as a risk instead of fixed, if applicable."
    )
    resolution: str = Field(
        default="",
        description=(
            "How it was fixed: the fixing specialist's own decisions and the files it "
            "changed. Set by the controller from that specialist's result."
        ),
    )


class TestRunRecord(BaseModel):
    """One executed test command and its outcome, kept as sprint evidence."""

    model_config = ConfigDict(extra="forbid")

    command: list[str] = Field(
        ..., description="The validation command that was run, e.g. ['npm', 'test']."
    )
    passed: bool = Field(..., description="Whether the command exited successfully.")
    summary: str = Field(default="", description="Short human-readable result summary.")


class RemediationCycle(BaseModel):
    """State for one sprint's test-fix-retest loop."""

    model_config = ConfigDict(extra="forbid")

    sprint_goal: str = Field(..., description="Which sprint this remediation cycle belongs to.")
    attempt: int = Field(default=0, ge=0, description="How many test-fix-retest cycles have run so far.")
    max_attempts: int = Field(default=DEFAULT_MAX_REMEDIATION_ATTEMPTS, gt=0)
    test_runs: list[TestRunRecord] = Field(default_factory=list)
    defects: list[Defect] = Field(default_factory=list)
    escalated: bool = Field(
        default=False, description="Set once the attempt limit is reached; a human must intervene."
    )


#: Words that carry no signal when comparing two defect descriptions.
_DEFECT_NOISE = frozenset({
    "a", "an", "and", "are", "as", "at", "because", "by", "cannot", "due", "for",
    "from", "in", "is", "issue", "issues", "of", "on", "or", "test", "tests",
    "that", "the", "to", "with", "fail", "fails", "failing", "failure", "error",
})


def _defect_terms(description: str) -> frozenset[str]:
    """The meaningful words of a defect description, for comparing two of them."""
    # Dots and dashes are kept inside a token so `jest.config.js` survives, then
    # stripped from the ends so a sentence-final period does not make `issues.`
    # a different word from `issues`.
    words = (word.strip(".-_") for word in re.findall(r"[A-Za-z0-9_.-]+", description.lower()))
    return frozenset(word for word in words if word not in _DEFECT_NOISE and len(word) > 2)


def recurrence_of(defect: Defect, earlier: Sequence[Defect]) -> Defect | None:
    """An already-fixed defect this one is a restatement of, if there is one.

    A defect marked fixed that comes back is not a new defect - it is evidence
    the fix did not work. Treating it as new spends another attempt on the same
    problem and tells the specialist nothing it does not already believe.

    Measured on one run, which exhausted all six remediation attempts:

        fixed: Regression test fails due to missing y18n module import
        fixed: Regression test fails due to improper import of y18n module.
        fixed: Regression tests fail due to y18n module import issues.

    One problem, three wordings, three attempts, each closed as done. Half the
    sprint's budget went on it and no application code was ever written.

    Similarity is deliberately crude - overlapping significant words, ignoring
    the connectives that every failure description shares. It only has to
    notice that two sentences are about the same thing, and a false negative
    just restores today's behaviour.
    """
    terms = _defect_terms(defect.description)
    if len(terms) < 2:
        return None
    for candidate in earlier:
        if candidate.status != "fixed":
            continue
        candidate_terms = _defect_terms(candidate.description)
        if not candidate_terms:
            continue
        overlap = len(terms & candidate_terms)
        smaller = min(len(terms), len(candidate_terms))
        if overlap >= 2 and overlap / smaller >= 0.6:
            return candidate
    return None


def failed_fix_tries(cycle: RemediationCycle, index: int) -> int:
    """How many times fixing this problem has failed: its own fixes, and the fix of the defect it restates.

    A defect marked fixed that comes back is recorded as a new one
    (`recurrence_of`); the fix that did not hold is a failed try of the same
    problem, and so is every one before it.
    """
    defect = cycle.defects[index]
    earlier = recurrence_of(defect, cycle.defects[:index])
    return int(defect.fix_attempts or 0) + (int(earlier.fix_attempts or 0) + 1 if earlier is not None else 0)


def recurring_defect_note(cycle: RemediationCycle) -> str:
    """What to tell the specialist about defects its earlier fixes did not close.

    Empty when nothing has recurred, so the caller can append it unconditionally.
    """
    lines: list[str] = []
    for index, defect in enumerate(cycle.defects):
        if defect.status != "open":
            continue
        earlier = recurrence_of(defect, cycle.defects[:index])
        if earlier is None:
            continue
        unproven = (
            ""
            if earlier.verified_by
            else " Nothing was ever recorded as running and passing for that fix, so "
            "the first thing to establish is whether it was run at all."
        )
        lines.append(
            f"- '{defect.description}' is the same problem as '{earlier.description}', "
            "which was already marked fixed. That fix did not work. Do not repeat it - "
            "find out why the previous change did not take effect, and say so plainly "
            f"if the cause is outside what you can change.{unproven}"
        )
    if not lines:
        return ""
    return (
        "\n\nThese defects have already been 'fixed' once and came back:\n"
        + "\n".join(lines)
    )


def start_remediation(
    sprint_goal: str, *, max_attempts: int = DEFAULT_MAX_REMEDIATION_ATTEMPTS
) -> RemediationCycle:
    """Create a fresh remediation cycle for a sprint, with zero attempts used."""
    return RemediationCycle(sprint_goal=sprint_goal, max_attempts=max_attempts)


#: Rounds a sprint may run in total, however they are counted. The budget
#: below can decline to charge a round against `max_attempts`; this is what
#: stops that becoming unbounded, and it is derived so the two cannot drift.
ROUNDS_PER_ATTEMPT_CEILING = 2


def record_test_run(
    cycle: RemediationCycle,
    *,
    command: list[str],
    passed: bool,
    summary: str = "",
    new_defects: list[Defect] | None = None,
    charge_the_budget: bool = True,
) -> RemediationCycle:
    """Record one executed test command and any newly discovered defects.

    `charge_the_budget` is False for a round that found nothing wrong with the
    product - only with the tests. The caller decides that, because deciding
    it means knowing which files are tests, and that is not this module's
    business.

    Measured on one run, which failed after three attempts with a working
    product: 43 of its 43 unit tests passed, all five features the brief names
    were built, and the cross-file checks found one stranded spec and a
    518-line product against a 500-line cap. Of the eleven defects it spent
    those attempts on, **seven were in `ui.pw.test.mjs`** - the Playwright
    suite the run had just written - and its second round was nothing else:

        round 1   2 in app.js, 2 in ui.pw.test.mjs
        round 2   0 in app.js, 3 in ui.pw.test.mjs
        round 3   2 in app.js, 2 in ui.pw.test.mjs

    A suite settling down is not the product failing, and charging it against
    a budget meant for the product is how a run dies with the product working.

    Raises:
        RemediationLimitExceeded: if the test failed and recording this
            attempt would exceed `max_attempts`, or if the sprint has run more
            rounds than any budget allows, so the caller pauses the sprint with
            an actionable error instead of looping forever.
    """
    # A round that passes while an earlier defect is still open has not cleared
    # the sprint: the workflow sends it straight back to remediation. Both
    # bounds below were written for failing rounds only, and `defect_remediation`
    # leaves a defect open on purpose when its fix names no regression test,
    # trusting "the next test round will count this as another failed attempt".
    # The next round passed. Measured on one run: a defect no stage could close
    # looped test_round_3 -> defect_fix_4_3 -> test_round_4 ... test_round_7 ->
    # defect_fix_8_3 with every round green and no limit ever reached.
    still_open = any(getattr(d, "status", "") == "open" for d in cycle.defects)
    cleared = passed and not still_open
    rounds_so_far = len(cycle.test_runs) + 1
    if not cleared and rounds_so_far > cycle.max_attempts * ROUNDS_PER_ATTEMPT_CEILING:
        raise RemediationLimitExceeded(
            f"Sprint '{cycle.sprint_goal}' has run {rounds_so_far} verification "
            f"rounds, the ceiling for a sprint allowed {cycle.max_attempts} "
            "remediation attempts. Rounds that found only test defects are not "
            "charged against those attempts, and this is what bounds that: the "
            "suite is not settling. A human must intervene."
        )

    next_attempt = cycle.attempt + (0 if cleared or not charge_the_budget else 1)
    if not cleared and next_attempt > cycle.max_attempts:
        raise RemediationLimitExceeded(
            f"Sprint '{cycle.sprint_goal}' has failed remediation {cycle.attempt} time(s), "
            f"reaching the limit of {cycle.max_attempts} attempts. Escalating instead of "
            "retrying automatically; a human must intervene."
        )

    return cycle.model_copy(
        update={
            "attempt": next_attempt,
            "test_runs": [
                *cycle.test_runs,
                TestRunRecord(command=command, passed=passed, summary=summary),
            ],
            "defects": [*cycle.defects, *(new_defects or [])],
            # Not cleared, rather than not passed. A round that passes while an
            # earlier defect is still open is charged an attempt like any other,
            # and when that attempt was the last, the sprint is out of them. It
            # used to be marked exhausted only by a round with defects of its
            # own, so this one left the count at its limit and said nothing:
            # the next failing round raised `RemediationLimitExceeded`, and one
            # run ended there - no re-plan, no Sprint Record - where every
            # other exhausted sprint is planned again.
            "escalated": (
                next_attempt >= cycle.max_attempts and not cleared and charge_the_budget
            ),
        }
    )


def mark_defect_fixed(
    cycle: RemediationCycle,
    defect_index: int,
    *,
    regression_test: str,
    verified_by: str = "",
    resolution: str = "",
) -> RemediationCycle:
    """Mark one defect fixed, requiring a regression test if the defect needs one.

    `verified_by` is the command the execution ledger confirms ran and exited 0,
    or "" when nothing was recorded. It does not gate the transition, and that
    is deliberate: an unproven fix still has to be *recorded* as a fix, or
    `recurrence_of` - which looks for an earlier defect marked fixed whose
    wording matches - goes blind, and losing "that fix did not work" would cost
    more than the false "fixed" it was meant to stop. What changes is that the
    report says which fixes were proven.

    Raises:
        ValueError: if the defect requires a regression test but none is given.
            A "fix" with no regression coverage is exactly what the workflow
            plan's gate forbids, so this is rejected here rather than left to
            a reviewer to catch later.
    """
    defect = cycle.defects[defect_index]
    if defect.regression_test_required and not regression_test:
        raise ValueError(
            f"Defect '{defect.description}' requires a regression test before it can be marked fixed."
        )
    # Counted here rather than in the graph because this is the one place a
    # defect's status changes to a terminal value. The counter is what tells an
    # operator the remediation loop is doing something; without it `/metrics`
    # reports `defects_resolved_total 0` on a system that has resolved defects,
    # which reads as "nothing has ever worked". See plan-part3 §3.1.
    from app.observability.metrics import MetricsTracker

    MetricsTracker.record_defect_resolution(resolved=True)
    updated_defects = list(cycle.defects)
    updated_defects[defect_index] = defect.model_copy(
        update={
            "status": "fixed",
            "regression_test": regression_test,
            "verified_by": verified_by,
            "resolution": resolution,
        }
    )
    return cycle.model_copy(update={"defects": updated_defects})


def accept_risk(cycle: RemediationCycle, defect_index: int, *, reason: str) -> RemediationCycle:
    """Explicitly record that a defect is being accepted as a risk instead of fixed.

    An accepted risk must have a stated reason so it is auditable later,
    distinct from a defect that was silently ignored.

    Deliberately not called by the graph. Accepting a known defect is a human
    judgement about risk tolerance, and letting the controller (or a model)
    make it automatically is exactly the "an agent decided to skip a gate"
    failure the workflow plan is built to prevent. Today the controller
    escalates to `failed` with the defect report instead, and a human resolves
    it. The Phase 6 web control plane is where this becomes a real, attributed
    human decision.
    """
    if not reason:
        raise ValueError("Accepting a defect as a risk requires a non-empty reason.")
    defect = cycle.defects[defect_index]
    # An accepted risk is a resolution the loop did not fix, and the counter has
    # a bucket for exactly that. Counting it here keeps the two outcomes from
    # being indistinguishable on the dashboard. See plan-part3 §3.1.
    from app.observability.metrics import MetricsTracker

    MetricsTracker.record_defect_resolution(resolved=False)
    updated_defects = list(cycle.defects)
    updated_defects[defect_index] = defect.model_copy(
        update={"status": "accepted_risk", "accepted_risk_reason": reason}
    )
    return cycle.model_copy(update={"defects": updated_defects})


def is_sprint_acceptable(cycle: RemediationCycle) -> bool:
    """Return whether this sprint may be accepted.

    A sprint is acceptable only when every defect is either fixed (with a
    regression test, if required) or explicitly accepted as a risk, and the
    remediation loop has not been escalated for exceeding its attempt limit.
    This mirrors the workflow plan's gate: "No sprint is accepted with
    failing mandatory tests, unowned defects, missing regression coverage, or
    undocumented accepted risk."
    """
    if cycle.escalated:
        return False
    for defect in cycle.defects:
        if defect.status == "open":
            return False
        if defect.status == "fixed" and defect.regression_test_required and not defect.regression_test:
            return False
        if defect.status == "accepted_risk" and not defect.accepted_risk_reason:
            return False
    return True


def build_defect_report(cycle: RemediationCycle) -> str:
    """Build a human-readable defect and test-evidence report for sprint acceptance records."""
    lines = [f"Sprint: {cycle.sprint_goal}", f"Remediation attempts: {cycle.attempt}/{cycle.max_attempts}"]
    for run in cycle.test_runs:
        outcome = "PASSED" if run.passed else "FAILED"
        lines.append(f"- {' '.join(run.command)}: {outcome} {run.summary}".rstrip())
    for defect in cycle.defects:
        # "fixed" on its own was a claim, not a finding. One run's final
        # message reported two of three defects fixed while the same suite
        # failed from the first test round to the last, because "fixed" meant
        # the specialist had named a test. Say which fixes anything actually
        # confirmed.
        state = defect.status
        if defect.status == "fixed":
            state = (
                f"fixed, verified by `{defect.verified_by}`"
                if defect.verified_by
                else "fixed, but nothing was recorded as running and passing"
            )
        lines.append(f"- Defect ({state}): {defect.description} [owner: {defect.owner}]")
    # A defect that was fixed and came back says something the list above does
    # not: that an earlier attempt was spent and achieved nothing.
    return "\n".join(lines) + recurring_defect_note(cycle)


__all__ = [
    "DEFAULT_MAX_REMEDIATION_ATTEMPTS",
    "Defect",
    "RemediationCycle",
    "RemediationLimitExceeded",
    "TestRunRecord",
    "accept_risk",
    "build_defect_report",
    "is_sprint_acceptable",
    "recurrence_of",
    "recurring_defect_note",
    "mark_defect_fixed",
    "record_test_run",
    "start_remediation",
]
