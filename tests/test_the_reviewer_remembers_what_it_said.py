"""A milestone review is a round in a conversation, not a fresh opinion.

Two runs died at the revision limit because the reviewer had no record of its
own previous findings:

    One run  round 2 minor    "init() ... no automated test exercises it"
                  round 3 blocking "init() ... has no automated test coverage"
                  - the same unchanged file, re-weighted, on the last round.

    One run  round 1 evidence "Confirmed 447 code lines ... is under the
                                    500-line brief limit"
                  round 3 major    "Application source files total 631 lines
                                    ... exceeding the brief's constraint"

`revision_comments` carries findings forward to the technical lead, so the
builders know what was asked. The reviewer was the one party to the argument
that could not hear itself.
"""

from __future__ import annotations

from app.agents.milestone_reviewer import (
    MilestoneReviewFinding,
    MilestoneReviewOutput,
    build_milestone_review_request,
    what_you_said_last_time,
)


def _review(*findings: tuple[str, str, str]) -> MilestoneReviewOutput:
    return MilestoneReviewOutput(
        status="changes_required",
        acceptance_evidence="read the files",
        documentation_reviewed=True,
        tests_reviewed=True,
        findings=[
            MilestoneReviewFinding(
                severity=severity,
                category=category,
                description=description,
                required_remediation="fix it",
                affected_files=["ui.js"],
            )
            for severity, category, description in findings
        ],
    )


THE_INIT_FINDING = (
    "minor",
    "testing",
    "init() is the main DOM wiring entry point exported from ui.js, but no "
    "automated test exercises it",
)


def test_the_previous_findings_come_back_verbatim() -> None:
    text = what_you_said_last_time(_review(THE_INIT_FINDING), 1, 3)

    assert "no automated test exercises it" in text
    assert "[minor]" in text


def test_an_optional_finding_stays_optional() -> None:
    """The rule that would have saved one run."""
    text = what_you_said_last_time(_review(THE_INIT_FINDING), 1, 3)

    assert "optional last round is optional this round" in text


def test_the_last_round_says_what_requiring_changes_costs() -> None:
    """The reviewer that failed one run raised its blocking finding on
    round three, where `changes_required` is not another round of fixes."""
    last = what_you_said_last_time(_review(THE_INIT_FINDING), 2, 3)

    assert "revision 3 of 3" in last
    assert "ENDS" in last


def test_an_earlier_round_says_how_many_are_left() -> None:
    text = what_you_said_last_time(_review(THE_INIT_FINDING), 1, 3)

    assert "revision 2 of 3" in text
    assert "ENDS" not in text


def test_a_first_review_is_told_nothing() -> None:
    """Nothing was said last time, because there was no last time."""
    assert what_you_said_last_time(None, 0, 3) == ""


def test_a_previous_review_with_no_findings_still_states_the_budget() -> None:
    """A round that accepted and was re-entered still spent a revision."""
    text = what_you_said_last_time(_review(), 2, 3)

    assert "revision 3 of 3" in text


def test_the_request_carries_it_to_the_reviewer() -> None:
    request = build_milestone_review_request(
        "wire up edit",
        ["ui.js"],
        "node --test: 12 passing",
        "no defects",
        ".",
        previous_review=_review(THE_INIT_FINDING),
        revisions_used=2,
        revisions_allowed=3,
    )
    content = request["messages"][0]["content"]

    assert "What you found on this milestone last time" in content
    assert "no automated test exercises it" in content
    assert "revision 3 of 3" in content


def test_a_request_without_a_previous_review_is_unchanged() -> None:
    request = build_milestone_review_request(
        "wire up edit", ["ui.js"], "12 passing", "no defects", "."
    )

    assert "What you found on this milestone last time" not in request["messages"][0]["content"]


def test_a_new_sprints_first_review_is_not_given_the_last_sprints_findings() -> None:
    """`sprint_advance_node` resets `milestone_revision_count` and leaves
    `milestone_review` in state, so the workflow gates on the count."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    call = source[source.index("previous_review=("):]
    call = call[: call.index("revisions_allowed")]

    assert 'state.get("milestone_revision_count", 0)' in call
