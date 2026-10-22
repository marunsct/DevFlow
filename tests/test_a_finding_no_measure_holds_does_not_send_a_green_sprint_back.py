"""With every test passing, a finding that names no criterion or test case does not send the sprint back.

One run's milestone review sent a sprint whose every acceptance and unit test
passed back twice, 35 minutes a round.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.graph import workflow
from app.graph.workflow import _findings_no_measure_holds


class _Finding(SimpleNamespace):
    def model_copy(self, update):
        return _Finding(**{**self.__dict__, **update})


class _Review(SimpleNamespace):
    def model_copy(self, update):
        return _Review(**{**self.__dict__, **update})


def _review():
    return _Review(findings=[
        _Finding(severity="major", description="The shutdown handler logs a vague message.", required_remediation="Reword it."),
        _Finding(severity="major", description="AC-17: a deleted note's id is reissued.", required_remediation="Never reuse ids."),
        _Finding(severity="major", description="The handler is wrong.", required_remediation="Make TC-AC-3-01 assert 404."),
        _Finding(severity="minor", description="Style.", required_remediation=""),
    ])


def test_a_finding_naming_no_measure_is_minor_while_every_test_passes(monkeypatch):
    monkeypatch.setattr(workflow, "_where_each_test_command_stands", lambda root: {"npm test": True, "npx playwright test": True})
    after = _findings_no_measure_holds(_review(), "/w")

    assert [f.severity for f in after.findings] == ["minor", "major", "major", "minor"]
    assert "recorded as a risk" in after.findings[0].description


def test_a_failing_test_leaves_every_finding_as_it_was(monkeypatch):
    monkeypatch.setattr(workflow, "_where_each_test_command_stands", lambda root: {"npm test": True, "npx playwright test": False})
    review = _review()
    assert _findings_no_measure_holds(review, "/w") is review


def test_no_test_record_leaves_every_finding_as_it_was(monkeypatch):
    monkeypatch.setattr(workflow, "_where_each_test_command_stands", lambda root: {})
    review = _review()
    assert _findings_no_measure_holds(review, "/w") is review


def test_the_reviewer_is_told_the_rule_in_plain_words():
    import re

    from app.agents.milestone_reviewer import MilestoneReviewFinding

    told = MilestoneReviewFinding.model_fields["severity"].description
    assert "names" in told and "AC-n" in told
    assert not re.search(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", told, re.I)
