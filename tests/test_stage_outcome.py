"""Recording what a stage decided, where someone can see it.

Measured on run-5d83e946: sprint 2's milestone was rejected and the reasons
appeared nowhere an operator could look. A stage's answer reaches the run
through its structured response, and a structured response is not a message,
so the event stream carried none of it. The reasons existed - in the next
stage's prompt.

The property that made this worth fixing is the direction of the bias. When
the model misbehaved and wrote its verdict as prose, `on_llm_end` published it
and the timeline showed everything; when the model behaved correctly, the
timeline showed nothing.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.graph.workflow import _outcome_summary


class Finding(BaseModel):
    severity: str
    description: str


class Review(BaseModel):
    status: str
    findings: list[Finding] = []


class Report(BaseModel):
    """A schema with neither field - a specialist's report."""

    summary: str


def test_a_rejection_says_what_has_to_change() -> None:
    summary = _outcome_summary(
        Review(
            status="changes_required",
            findings=[
                Finding(severity="blocking", description="tests copy the code"),
                Finding(severity="minor", description="no aria labels"),
            ],
        )
    )

    assert "changes_required" in summary
    assert "2 finding(s)" in summary
    assert "[blocking] tests copy the code" in summary
    assert "no aria labels" in summary


def test_an_acceptance_is_recorded_too() -> None:
    """A passed milestone is the other half of "why did this sprint end"."""
    assert _outcome_summary(Review(status="passed")) == "Outcome: passed"


def test_only_the_first_three_findings_are_named() -> None:
    review = Review(
        status="changes_required",
        findings=[Finding(severity="minor", description=f"thing {i}") for i in range(6)],
    )

    summary = _outcome_summary(review)

    assert "6 finding(s)" in summary
    assert "thing 0" in summary and "thing 2" in summary
    assert "thing 3" not in summary
    assert "and 3 more" in summary


def test_a_schema_with_no_verdict_narrates_nothing() -> None:
    """A specialist returning a report has no outcome to record, and silence is
    the right amount of narration for it."""
    assert _outcome_summary(Report(summary="built the thing")) == ""


def test_an_enum_status_is_rendered_by_its_value() -> None:
    import enum

    class Status(enum.Enum):
        CHANGES_REQUIRED = "changes_required"

    class Enumerated(BaseModel):
        status: Status

    assert "changes_required" in _outcome_summary(Enumerated(status=Status.CHANGES_REQUIRED))


def test_publishing_never_raises_on_a_stage_with_no_stream() -> None:
    """Narration is never load-bearing; an empty callback list is normal."""
    from app.server.agent_stream import publish_stage_outcome

    publish_stage_outcome([], "Outcome: passed")
    publish_stage_outcome([], "")


def test_the_outcome_is_published_as_a_log_event_on_its_stage() -> None:
    from app.server.agent_stream import AgentActivityStream, publish_stage_outcome

    published: list[tuple[str, str]] = []

    class Recording(AgentActivityStream):
        def _publish(self, event_type, message, metadata=None):  # noqa: ANN001
            published.append((event_type, message))

    publish_stage_outcome([Recording("run-1", "milestone_review")], "Outcome: passed")

    assert published == [("log", "Outcome: passed")]
