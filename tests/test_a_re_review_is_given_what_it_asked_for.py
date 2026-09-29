"""A second review of a specification is told what the first one asked for.

One run's architecture reviewer sent a to-do list specification back three
times, raising two new major findings each round - a partial-update contract,
then an ES module setting, then that a checkbox should show whether its task
is done - and never said whether the previous ones were answered. It was given
the specification and nothing else, so every round was a first reading.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from app.agents.architecture_reviewer import ArchitectureReviewFinding, build_architecture_review_request

FINDING = ArchitectureReviewFinding(
    severity="major",
    description="updateTask validation contradicts partial updates.",
    evidence="API contracts: updateTask.",
    required_remediation="Make updateTask's fields optional.",
)


def _brief(tmp_path: Path, **kwargs: object) -> str:
    request = build_architecture_review_request("# Spec\nupdateTask(id, fields)", str(tmp_path), "", **kwargs)
    return " ".join(request["messages"][0]["content"].split())


def test_a_first_review_is_unchanged(tmp_path: Path) -> None:
    assert "What your review of the previous version asked for" not in _brief(tmp_path)


def test_a_re_review_is_given_its_earlier_findings(tmp_path: Path) -> None:
    brief = _brief(tmp_path, earlier=[FINDING], revision=1)

    assert "What your review of the previous version asked for (revision 1)" in brief
    assert "[major] updateTask validation contradicts partial updates." in brief
    assert "Required remediation: Make updateTask's fields optional." in brief
    assert "Check each of these first: resolved, or still open" in brief


def test_findings_restored_as_plain_data_are_read_too(tmp_path: Path) -> None:
    """A checkpoint can hand the previous review back as a dict."""
    brief = _brief(tmp_path, earlier=[FINDING.model_dump()], revision=2)

    assert "[major] updateTask validation contradicts partial updates." in brief


def test_a_new_finding_has_a_bar_to_clear(tmp_path: Path) -> None:
    brief = _brief(tmp_path, earlier=[FINDING], revision=1)

    assert "would build something that fails a requirement of the brief" in brief
    assert "Something they would get right without being told" in brief
    assert "is minor" in brief


def test_the_workflow_passes_the_previous_review_in() -> None:
    from app.graph import workflow

    source = inspect.getsource(workflow)
    call = source.split("request = build_architecture_review_request(", 1)[1].split("\n        )\n", 1)[0]

    assert "earlier=" in call and "previous_review" in call
    assert 'revision=state.get("architecture_revision_count", 0)' in call
