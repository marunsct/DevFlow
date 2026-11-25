"""A security finding names its harm; one that names none is a code note; a recorded finding is not raised again (PA.17).

Measured on one run's security reviews (2026-11-25 per-agent audit, role 18): its critical finding was a missing type
import, its info findings an unused model class and comments in a test file - five of six findings were not about
security - the second review of the same sprint raised three of them again, and the milestone review repeated two as
suggestions.
"""
from __future__ import annotations

import re

import pytest

from app.agents.milestone_reviewer import MilestoneReviewOutput, without_repeats_of_other_reviews
from app.agents.security_reviewer import (
    NAME_THE_HARM, SecurityFinding, SecurityReviewOutput, as_recorded, build_security_review_request,
)
from app.sprint.record import findings_of

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
IMPORT = "The route module uses the Note type without importing it, so type checking fails"
UNUSED = "The TaskModel class in models.py is defined and never used anywhere"


def _finding(severity: str, description: str, harm: str = "", category: str = "isolation") -> dict:
    found = {"severity": severity, "category": category, "description": description, "remediation": "change it"}
    return {**found, "harm": harm} if harm else found


def _review(*findings: dict) -> SecurityReviewOutput:
    return SecurityReviewOutput.model_validate({"status": "findings", "findings": list(findings)})


def test_a_critical_finding_that_names_no_harm_is_a_code_note_and_cannot_hold_the_sprint() -> None:
    review = as_recorded(_review(_finding("critical", IMPORT)))

    (finding,) = review.findings
    assert finding.category == "code_note"
    assert finding.severity not in ("critical", "high")
    assert not any(record["gating"] for record in findings_of(review, "security", 1))


@pytest.mark.parametrize("harm", ["", "none", "N/A", "no security impact"])
def test_a_harm_that_says_nothing_is_no_harm(harm: str) -> None:
    (finding,) = as_recorded(_review(_finding("high", IMPORT, harm))).findings
    assert finding.category == "code_note" and finding.severity == "low"


def test_a_finding_that_names_its_harm_keeps_its_severity() -> None:
    harm = "Any visitor can delete another user's notes by sending their id"

    (finding,) = as_recorded(_review(_finding("high", "DELETE /notes/:id checks no owner", harm, "permissions"))).findings

    assert (finding.severity, finding.category) == ("high", "permissions")


def test_a_finding_the_sprint_already_recorded_is_not_raised_again_unless_it_holds_the_sprint() -> None:
    harm = "Any visitor can delete another user's notes by sending their id"
    recorded = [UNUSED, "DELETE /notes/:id checks no owner of the note"]
    second = _review(
        _finding("info", "The TaskModel class defined in models.py is never used"),
        _finding("critical", "DELETE /notes/:id checks no owner of the note", harm, "permissions"),
        _finding("low", "Error responses include the stack trace", "A visitor learns the server's file layout"),
    )

    kept = as_recorded(second, recorded).findings

    assert [f.description for f in kept] == ["DELETE /notes/:id checks no owner of the note",
                                            "Error responses include the stack trace"]


def test_a_review_left_with_nothing_new_passes() -> None:
    review = as_recorded(_review(_finding("info", UNUSED)), [UNUSED])
    assert review.status == "passed" and review.findings == []


def test_a_category_from_another_review_s_words_keeps_the_review() -> None:
    finding = SecurityFinding.model_validate(_finding("low", UNUSED, category="code_quality"))
    assert finding.category == "other"


def test_the_reviewer_is_told_what_the_sprint_recorded(tmp_path) -> None:
    request = build_security_review_request([], "perms", str(tmp_path), recorded=[UNUSED])
    assert UNUSED in request["messages"][0]["content"]


def test_the_reviewer_is_told_to_name_the_harm() -> None:
    from app.agents import security_reviewer

    assert NAME_THE_HARM in security_reviewer._SYSTEM_PROMPT
    assert "harm" in SecurityFinding.model_json_schema()["properties"]


def test_the_milestone_review_does_not_repeat_another_review_s_finding_below_major() -> None:
    sprint = [{"source": "security", "description": UNUSED, "severity": "low", "round": 1},
              {"source": "milestone", "description": "The list is never sorted by date", "severity": "minor",
               "round": 1}]
    review = MilestoneReviewOutput.model_validate({
        "status": "accepted", "acceptance_evidence": "e", "documentation_reviewed": True, "tests_reviewed": True,
        "findings": [
            {"severity": "suggestion", "category": "code_quality", "required_remediation": "remove it",
             "description": "TaskModel class in models.py is never used anywhere"},
            {"severity": "major", "category": "code_quality", "required_remediation": "remove it",
             "description": "The TaskModel class in models.py is defined and never used anywhere"},
            {"severity": "minor", "category": "correctness", "required_remediation": "sort it",
             "description": "The list is never sorted by date"},
        ]})

    kept = without_repeats_of_other_reviews(review, sprint).findings

    assert [f.severity for f in kept] == ["major", "minor"]


def test_the_security_review_stage_records_a_note_as_a_note_and_a_repeat_not_at_all(tmp_path) -> None:
    from app.agents.specialists import SpecialistOutput
    from app.state import RepositoryContext
    from workflow_nodes import run_node

    (tmp_path / "server.js").write_text("const notes = [];\n")
    answered = _review(_finding("critical", IMPORT),
                       _finding("info", "The TaskModel class defined in models.py is never used"))
    asked: list[str] = []

    def gated(state, config, **kwargs):
        asked.append(kwargs["initial_request"]["messages"][-1]["content"])
        return {kwargs["output_key"]: answered}

    state = {
        "repository": RepositoryContext(root_path=str(tmp_path), branch="main", commit="HEAD", status="clean"),
        "specialist_outputs": {"specialist_backend_0": SpecialistOutput(changed_files=["server.js"])},
        "sprint_findings": [{"round": 1, "source": "security", "severity": "info", "description": UNUSED,
                             "remediation": "", "gating": False}],
    }

    update = run_node("security_review", state, str(tmp_path), {
        "app.graph.workflow._run_gated_agent": gated,
        "app.graph.workflow.create_security_reviewer_agent": lambda *a, **k: object(),
    })

    assert UNUSED in asked[0]
    new = update["sprint_findings"][1:]
    assert [(f["severity"], f["gating"]) for f in new] == [("low", False)]


def test_the_new_words_use_none_of_the_banned_ones(tmp_path) -> None:
    request = build_security_review_request([], "perms", str(tmp_path), recorded=["x"])["messages"][0]["content"]
    described = str(SecurityFinding.model_json_schema()["properties"]["harm"]["description"])
    assert not [text for text in (NAME_THE_HARM, request, described) if BANNED.search(text)]
