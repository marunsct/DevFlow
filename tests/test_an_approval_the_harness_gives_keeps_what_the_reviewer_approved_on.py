"""When the harness approves the specification on the reviewer's behalf, the approval keeps what the reviewer said (LF.1511).

Measured on one medium run in thorough delivery: the reviewer approved with three approval conditions, four accepted
risks and three earlier findings each resolved with where. The workflow's own design checks overturned the approval,
the architect revised, and the harness approved without a second review with an empty review: state and
`docs/architecture_review.md` held "No findings", "None answered" and no conditions or risks.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from workflow_nodes import a_specification, run_node

CONDITIONS = [
    "The error_catalogue section (lines 230-251) must remain present and contain all error codes referenced "
    "elsewhere in the spec",
    "Every route listed in the interface contract keeps the status codes the contract gives it",
    "The data model section stays the one source of every stored field's name and type",
]
RISKS = [
    "The signing secret defaults to a deterministic seed when the environment sets none",
    "Rate limiting is per process, so two processes allow twice the stated rate",
]


def _the_reviewer_s_last_review():
    """The reviewer's approval as state holds it once the workflow's own check overturned it."""
    from app.agents.architecture_reviewer import ArchitectureReviewFinding, ArchitectureReviewOutput

    return ArchitectureReviewOutput(
        status="changes_required",
        findings=[ArchitectureReviewFinding(severity="major", description="The brief's reminders are deferred.",
                                            evidence="Deferred scope", required_remediation="Specify reminders.")],
        approval_conditions=CONDITIONS,
        accepted_risks=RISKS,
        earlier_findings=[{"number": n, "resolved": True, "where": f"Section {n} now states it."} for n in (1, 2, 3)],
    )


#: The two ways the harness approves without a second review, each with what turns it on.
WAYS = {
    "the revision settled the workflow's own findings": (
        {"HARNESS_FINDINGS_RECHECKED": "on"}, False, {"approved_but_for_the_harness": ["deferrals"]}),
    "decided after one revision": ({"ONE_DESIGN_REVIEW": "on"}, True, {}),
}


@pytest.mark.parametrize("way", sorted(WAYS))
def test_the_harness_s_approval_keeps_the_reviewer_s_conditions_risks_and_answers(monkeypatch, tmp_path, way):
    switches, fast, extra = WAYS[way]
    for name, value in switches.items():
        monkeypatch.setenv(name, value)
    asked = []
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "document": SimpleNamespace(text="Notes over HTTP."),
        "technical_specification": a_specification(),
        "architecture_review": _the_reviewer_s_last_review(),
        "architecture_revision_count": 1,
        "decisions": [],
        **extra,
    }
    nothing = lambda *args, **kwargs: None  # noqa: E731 - none of the workflow's checks finds anything now
    update = run_node("architecture_review", state, str(tmp_path), {
        "app.graph.workflow._fast_delivery": lambda: fast,
        "app.graph.workflow._review_enabled": lambda state, point: False,
        "app.graph.workflow.create_architecture_reviewer_agent": lambda **kwargs: MagicMock(),
        "app.graph.workflow._run_gated_agent": lambda *args, **kwargs: asked.append(True) or {},
        "app.graph.workflow._a_success_measure_the_specification_drops": nothing,
        "app.graph.workflow._a_brief_feature_the_specification_defers": nothing,
        "app.graph.workflow._contract_lines_nothing_can_read": nothing,
        "app.graph.workflow._the_same_command_in_another_order": nothing,
        "app.graph.workflow._behaviour_the_specification_gives_kept_files": nothing,
        "app.graph.workflow._a_kept_signature_the_specification_calls_otherwise": nothing,
        "app.graph.one_design_review.contradictions": lambda specification: [],
    })

    assert not asked, "approved without a second review"
    approved = update["architecture_review"]
    assert approved.status == "approved" and approved.findings == []
    assert approved.approval_conditions == CONDITIONS
    assert approved.accepted_risks == RISKS
    assert [(a.number, a.resolved) for a in approved.earlier_findings] == [(1, True), (2, True), (3, True)]
    document = (tmp_path / "docs" / "architecture_review.md").read_text(encoding="utf-8")
    assert CONDITIONS[0] in document and RISKS[0] in document and "Section 2 now states it." in document
    assert "None answered" not in document
    assert "3 approval condition(s) and 2 accepted risk(s) are carried" in update["decisions"][-1]["rationale"]
