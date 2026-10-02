"""A severity a reviewer is given and the workflow ignores is decoration.

Every reviewer here is handed a severity vocabulary and asked to grade its
findings. Until this gate, nothing routed on the grade: `status` alone decided,
so a reviewer that wrote `changes_required` over nothing but `minor` findings
sent the work back exactly as hard as one that found a blocking defect.

That killed one run. Its six architecture reviews went:

    1   8 findings, 2 blocking   - legitimate
    2   4 findings, all minor    - sent back
    3  15 findings, all minor    - sent back
    4   4 findings, all minor    - sent back
    5  10 findings, 3 major      - escalated
    6  10 findings, the same 3   - limit reached, run failed

Rounds 2, 3 and 4 were revisions nothing had asked for. The specification
shrank from 205 lines to 134 across them while the reviewer asked for more
detail, and by round 5 it was demanding constructors, method signatures and
parameter types - implementation detail a specification does not carry.

`_GATING_SEVERITIES` already existed when that run failed. It was used only to
format the message printed *after* the revision limit was reached.
"""

from __future__ import annotations

from app.agents.architecture_reviewer import (
    ArchitectureReviewFinding,
    ArchitectureReviewOutput,
)
from app.graph.workflow import _findings_that_block


def _finding(severity: str) -> ArchitectureReviewFinding:
    return ArchitectureReviewFinding(
        severity=severity,
        description="something",
        evidence="somewhere",
        required_remediation="change it",
    )


def _review(*severities: str) -> ArchitectureReviewOutput:
    return ArchitectureReviewOutput(
        status="changes_required",
        findings=[_finding(s) for s in severities],
    )


def test_minor_findings_do_not_block() -> None:
    """Rounds 2, 3 and 4 of one run."""
    assert _findings_that_block(_review("minor", "minor", "minor", "minor")) == []


def test_blocking_and_major_do_block() -> None:
    assert len(_findings_that_block(_review("blocking", "minor"))) == 1
    assert len(_findings_that_block(_review("major", "minor", "major"))) == 2


def test_informational_and_suggestion_do_not_block() -> None:
    """The two vocabularies' lowest rungs. `suggestion` belongs to the
    milestone reviewer, `informational` to the architecture reviewer."""
    assert _findings_that_block(_review("informational")) == []


def test_the_security_vocabulary_is_covered_too() -> None:
    """Four reviewers, four vocabularies. A gating set that covered only one
    would gate that reviewer and let the others through - or, as it did, gate
    none of them.
    """
    from types import SimpleNamespace

    security = SimpleNamespace(
        findings=[
            SimpleNamespace(severity="critical"),
            SimpleNamespace(severity="high"),
            SimpleNamespace(severity="medium"),
            SimpleNamespace(severity="low"),
            SimpleNamespace(severity="info"),
        ]
    )

    blocking = _findings_that_block(security)

    assert [f.severity for f in blocking] == ["critical", "high"]


def test_severity_is_matched_regardless_of_case_or_spacing() -> None:
    from types import SimpleNamespace

    review = SimpleNamespace(findings=[SimpleNamespace(severity="  Blocking ")])

    assert len(_findings_that_block(review)) == 1


def test_a_review_with_no_findings_blocks_nothing() -> None:
    """It also must not raise - a reviewer that returns nothing is handled
    further on, by a message that says it asked for changes and named none."""
    from types import SimpleNamespace

    assert _findings_that_block(SimpleNamespace(findings=[])) == []
    assert _findings_that_block(SimpleNamespace(findings=None)) == []
    assert _findings_that_block(SimpleNamespace()) == []


def test_both_reviewers_route_on_it() -> None:
    """Fixing the reviewer that happened to fail is how this codebase has
    shipped the same bug four times. Architecture failed one run;
    milestone had the identical hole and no run had reached it yet.
    """
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    architecture = source.index("def architecture_review_node")
    milestone = source.index("def milestone_review_node")

    # `_findings_that_block(review, root)` since the scope gate: the root is
    # what lets a finding about something nobody asked for be capped rather
    # than blocking. Matched on the call rather than its exact arguments so
    # the next argument added here does not read as the routing being lost.
    assert "_findings_that_block(review" in source[architecture:architecture + 4000]
    assert "_findings_that_block(review" in source[milestone:milestone + 8000]


def test_both_reviewers_are_given_the_workspace_to_judge_scope() -> None:
    """The gate is inert without it, and inert would look like passing."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    for node in ("def architecture_review_node", "def milestone_review_node"):
        start = source.index(node)
        window = source[start:start + 8000]
        call = window[window.index("_findings_that_block(review"):][:120]
        assert "root_path" in call, f"{node} judges scope without the workspace"
