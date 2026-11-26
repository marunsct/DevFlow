"""A gating design finding that says a section is missing is resolved once the specification has it, even when the
re-review says so in its own words (LF.1504).

Measured on a medium run: after six revisions the run waited for a person on one open finding, which said the
specification had no `error_catalogue` section. The specification had had an "Error Catalogue" of eleven entries for
several revisions, and the re-review said it was resolved ("## Error Catalogue section added at line 210, listing
DUPLICATE_EMAIL (409), ..."), but the quote rule (LF.1440) refused it: the answer quoted no six consecutive words of the
specification. The finding, the re-review's answer and the specification's sections are the run's own; the findings a
search does not answer are from other runs' reviews.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.architecture_reviewer import ArchitectureReviewFinding, ArchitectureReviewOutput, EarlierFindingAnswer
from app.graph import design_gate, workflow
from app.graph.workflow import _format_finding
from workflow_nodes import a_specification, run_node

CAPTURED = Path(__file__).parent / "captured"
SPECIFICATION = (CAPTURED / "technical-specification-an-error-catalogue-added.md").read_text()
RECORD = json.loads((CAPTURED / "design-finding-a-missing-section-answered-in-other-words.json").read_text())
G6 = ArchitectureReviewFinding(**RECORD["finding"])
IN_ITS_OWN_WORDS = RECORD["re_review_answer"]["where"]
NOT_SPECIFIED = ArchitectureReviewFinding(**json.loads((CAPTURED / "design-finding-a-section-not-specified.json").read_text()))
NOT_BY_A_SEARCH = [ArchitectureReviewFinding(**finding) for finding in
                   json.loads((CAPTURED / "design-findings-a-search-does-not-answer.json").read_text())]
FIRST_ENTRY = "DUPLICATE_EMAIL (409 Conflict): Returned when POST /api/v1/auth/register is called with an email"
FIRST_CONTRACT = "UserCreate: {email: 'test@example.com', username: 'testuser', password: 'password123'}."
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _section(title: str, text: str = SPECIFICATION) -> list[str]:
    lines = text.splitlines()
    start = lines.index(f"## {title}")
    end = next((at for at in range(start + 1, len(lines)) if lines[at].startswith("## ")), len(lines))
    return [line[2:] for line in lines[start + 1:end] if line.startswith("- ")]


def _without(title: str) -> str:
    """The specification as the finding was raised on: the section rendered empty."""
    lines = SPECIFICATION.splitlines()
    start = lines.index(f"## {title}")
    end = next(at for at in range(start + 1, len(lines)) if lines[at].startswith("## "))
    return "\n".join([*lines[:start + 1], "_Not specified._", "", *lines[end:]])


AS_RENDERED = SPECIFICATION
AS_STRUCTURED = a_specification(**{field: _section(title) for field, title in (
    ("reliability_and_observability", "Reliability and Observability"), ("data_contracts", "Data Contracts"),
    ("error_catalogue", "Error Catalogue"), ("specialist_advice_decisions", "Specialist Advice and Decisions"))})


@pytest.fixture(autouse=True)
def _delivered_thoroughly(monkeypatch):
    monkeypatch.setattr(workflow, "_fast_delivery", lambda: False)


def _open(finding: ArchitectureReviewFinding, **fields) -> dict:
    return {"number": 6, "source": design_gate.REVIEWER, "text": _format_finding(finding), "raised": 1,
            "status": "open", "finding": finding.model_dump(), **fields}


def _re_reviewed(tmp_path, specification, finding=G6, where=IN_ITS_OWN_WORDS):
    state = {
        "architecture_review": ArchitectureReviewOutput(status="changes_required", findings=[finding]),
        "technical_specification": specification,
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "decisions": [],
        design_gate.KEY: {"round": 5, "findings": [_open(finding)]},
    }
    review = ArchitectureReviewOutput(status="approved", findings=[], earlier_findings=[
        EarlierFindingAnswer(number=1, resolved=True, where=where)])
    update: dict = {}
    after = design_gate.after_a_review(state, update, review, {}, [])
    [entry] = update[design_gate.KEY]["findings"]
    return entry, after, update


@pytest.mark.parametrize("specification", [AS_RENDERED, AS_STRUCTURED], ids=["rendered", "structured"])
def test_a_missing_section_the_re_review_says_was_added_is_resolved_on_the_specification_s_own_first_line(
        tmp_path, specification):
    entry, after, update = _re_reviewed(tmp_path, specification)

    assert entry["status"] == "resolved"
    assert after.findings == [] and after.status == "approved"
    [decision] = update["decisions"]
    assert decision["rationale"].startswith(f"resolved: checked by the harness - Error Catalogue: {FIRST_ENTRY}")


def test_a_section_reported_as_not_specified_is_resolved_once_it_is(tmp_path):
    entry, _, update = _re_reviewed(tmp_path, AS_RENDERED, finding=NOT_SPECIFIED, where="Populated now.")

    assert entry["status"] == "resolved"
    assert update["decisions"][0]["rationale"].startswith(
        f"resolved: checked by the harness - Data Contracts: {FIRST_CONTRACT}")


@pytest.mark.parametrize(("finding", "title"), [(G6, "Error Catalogue"), (NOT_SPECIFIED, "Data Contracts")],
                         ids=["does-not-exist", "not-specified"])
def test_while_the_section_is_still_missing_the_finding_stays_open_and_goes_back(tmp_path, finding, title):
    entry, after, _ = _re_reviewed(tmp_path, _without(title), finding=finding)

    assert entry["status"] == "open"
    assert [carried.description for carried in after.findings] == [finding.description]


@pytest.mark.parametrize("finding", NOT_BY_A_SEARCH, ids=[
    "names-sections-as-references", "says-a-version-is-wrong", "a-section-is-the-subject-of-another-verb"])
def test_a_finding_that_is_not_about_a_missing_section_still_needs_the_reviewer_s_quote(tmp_path, finding):
    """Each names sections the specification has, but not as missing: as where it looked, as where something is
    wrong, or as what states the rule another section breaks."""
    entry, _, _ = _re_reviewed(tmp_path, a_specification(), finding=finding, where="Fixed in the revision.")

    assert entry["status"] == "open"


def _at_the_gate(tmp_path, specification, **fields) -> dict:
    """The state the escalation reads after the sixth revision left G6 open."""
    return {
        "decisions": [], "architecture_revision_count": 6,
        "technical_specification": specification,
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "escalation": {"kind": "design", "error": "The architecture reviewer still asked for changes.",
                       "findings": [_format_finding(G6)]},
        design_gate.KEY: {"round": 6, "findings": [_open(G6, **fields)]},
    }


NOBODY_ASKED = {"app.graph.workflow._review_enabled": lambda state, point: False,
                "app.agents.specification_rulings.settle": lambda *args, **kwargs: [],
                "app.graph.workflow._a_model_to_revise_with": lambda model: None}


def test_before_the_run_waits_for_a_person_a_finding_the_specification_answers_is_resolved(tmp_path):
    update = run_node("escalation", _at_the_gate(tmp_path, AS_STRUCTURED), str(tmp_path), NOBODY_ASKED)

    assert update["stage"] != "user_review_escalation"
    assert [entry["status"] for entry in update[design_gate.KEY]["findings"]] == ["resolved"]
    [checked] = [d for d in update["decisions"] if d["decision"] == "resolved before waiting for a person"]
    assert f"Error Catalogue: {FIRST_ENTRY}" in checked["rationale"]


def test_a_finding_the_last_re_review_said_is_still_open_is_left_to_the_person(tmp_path):
    update = run_node("escalation", _at_the_gate(tmp_path, AS_STRUCTURED, still_open=6), str(tmp_path), NOBODY_ASKED)

    assert update["stage"] == "user_review_escalation"


def test_what_the_harness_s_check_records_names_no_product_word(tmp_path):
    _, _, update = _re_reviewed(tmp_path, AS_STRUCTURED)
    at_the_gate = run_node("escalation", _at_the_gate(tmp_path, AS_STRUCTURED), str(tmp_path), NOBODY_ASKED)

    for decision in [*update["decisions"], *at_the_gate["decisions"]]:
        written = decision["question"] + decision["decision"] + decision["rationale"].split(" - Error Catalogue: ")[0]
        assert not BANNED.search(written), written
