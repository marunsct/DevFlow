"""Behind `MILESTONE_EVIDENCE_GATE` (harness review G3, docs/measuring.md M7): a milestone finding sends the sprint
back only when a failing test, criterion or underline shows it - the code review's rule.

Measured on one run: the sprint went back on a reviewer's reading of the code (a `KeyError` on a malformed stored
record) that no test showed, about twenty minutes; the product scored the same either way.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import engineering, milestone_evidence, workflow

SHOWN = SimpleNamespace(severity="blocking", description="[AC-5] delete answers 500", recommendation="")
UNSHOWN = SimpleNamespace(severity="blocking", description="load_notes() raises KeyError on a record missing 'id'",
                          recommendation="skip such records")


def _review():
    return SimpleNamespace(findings=[SHOWN, UNSHOWN], status="changes_required")


def _state(tmp_path):
    return {"repository": SimpleNamespace(root_path=str(tmp_path))}


def test_on_only_the_finding_a_test_shows_sends_the_sprint_back(tmp_path, monkeypatch):
    monkeypatch.setenv("MILESTONE_EVIDENCE_GATE", "on")
    monkeypatch.setattr(workflow, "_findings_that_block", lambda review, root=None: list(review.findings))
    monkeypatch.setattr(engineering, "what_shows_it",
                        lambda state, f: "The acceptance suite shows AC-5 failing." if "AC-5" in f.problem else "")
    assert workflow._milestone_findings_that_block(_state(tmp_path), _review()) == [SHOWN]


def test_off_every_blocking_finding_sends_it_back_as_before(tmp_path, monkeypatch):
    monkeypatch.setenv("MILESTONE_EVIDENCE_GATE", "off")
    monkeypatch.setattr(workflow, "_findings_that_block", lambda review, root=None: list(review.findings))
    assert workflow._milestone_findings_that_block(_state(tmp_path), _review()) == [SHOWN, UNSHOWN]


def test_the_switch_is_off_in_code():
    assert milestone_evidence.ON_BY_DEFAULT is False
