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


def test_both_reviewers_route_on_it(tmp_path) -> None:
    """Fixing the reviewer that happened to fail is how this codebase has
    shipped the same bug four times. Architecture failed one run;
    milestone had the identical hole and no run had reached it yet.

    Each is asked for changes over minor findings only, and goes on; over a
    major one, and sends the work back.
    """
    from workflow_nodes import (
        a_design_finding, a_milestone_finding, a_milestone_review, a_milestone_verdict, an_architecture_review,
    )

    minor = ArchitectureReviewOutput(status="changes_required", findings=[a_design_finding("minor")])
    major = ArchitectureReviewOutput(status="changes_required", findings=[a_design_finding("major")])
    assert an_architecture_review(tmp_path, minor)[0]["stage"] == "scaffold"
    assert an_architecture_review(tmp_path, major)[0]["stage"] == "principal_architect"

    minor = a_milestone_verdict("changes_required", a_milestone_finding("minor"))
    major = a_milestone_verdict("changes_required", a_milestone_finding("major"))
    assert a_milestone_review(tmp_path, minor)["stage"] == "release"
    assert a_milestone_review(tmp_path, major)["stage"] == "technical_lead"


def test_the_milestone_review_routes_on_its_own_gate(tmp_path, monkeypatch) -> None:
    """The milestone review's gate adds the evidence rule (G3): a major finding nothing shows is advice, and the
    sprint goes on; one a test shows sends it back."""
    from app.graph import engineering
    from workflow_nodes import a_milestone_finding, a_milestone_review, a_milestone_verdict

    monkeypatch.setenv("MILESTONE_EVIDENCE_GATE", "on")
    unshown = a_milestone_verdict("changes_required", a_milestone_finding("major", description="load() may raise"))
    shown = a_milestone_verdict("changes_required", a_milestone_finding("major", description="[AC-5] delete fails"))
    monkeypatch.setattr(engineering, "what_shows_it",
                        lambda state, f: "The suite shows AC-5 failing." if "AC-5" in f.problem else "")

    assert a_milestone_review(tmp_path, unshown)["stage"] == "release"
    assert a_milestone_review(tmp_path, shown)["stage"] == "technical_lead"


def test_both_reviewers_are_given_the_workspace_to_judge_scope(tmp_path, monkeypatch) -> None:
    """The gate is inert without it, and inert would look like passing.

    A major finding about something this workspace's scope does not ask for is
    capped rather than blocking, in both reviews.
    """
    from types import SimpleNamespace

    from app.analysis import scope_attestation
    from app.graph import workflow
    from workflow_nodes import (
        a_design_finding, a_milestone_finding, a_milestone_review, a_milestone_verdict, an_architecture_review,
    )

    asked_about = []
    monkeypatch.setattr(scope_attestation, "categories_in_scope", lambda root: asked_about.append(root) or {"correctness"})
    monkeypatch.setattr(scope_attestation, "out_of_scope_reason",
                        lambda category, in_scope: "nobody asked for it" if category == "security" else "")

    # A design finding carries no category: what matters is that its review asks the workspace at all.
    design = ArchitectureReviewOutput(status="changes_required", findings=[a_design_finding("major")])
    assert an_architecture_review(tmp_path, design)[0]["stage"] == "principal_architect"
    assert asked_about and set(asked_about) == {str(tmp_path)}

    asked_about.clear()
    milestone = a_milestone_verdict("changes_required", a_milestone_finding("major", category="security"))
    assert a_milestone_review(tmp_path, milestone)["stage"] == "release"
    assert asked_about and set(asked_about) == {str(tmp_path)}
    assert workflow._milestone_findings_that_block({"repository": SimpleNamespace(root_path=str(tmp_path))}, milestone) == []
