"""A specification the reviewer approved, sent back only by the workflow's own checks, is rechecked by those checks.

Behind `HARNESS_FINDINGS_RECHECKED`, off until measured. Measured on one day: in three runs the reviewer approved, a
workflow check added a finding, and after the revision a whole second review raised new findings and escalated.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from app import switches
from app.graph import workflow
from app.observability import provenance

BRIEF = "# Notes\n\n- Notes with tags, due dates and reminders.\n"


def _state(**extra):
    return {"document": SimpleNamespace(text=BRIEF), "architecture_revision_count": 1, **extra}


def test_a_finding_the_revision_settled_is_no_longer_open_and_one_it_did_not_is():
    settled = "## Features\n- Notes carry tags, due dates and reminders.\n"
    still = "## Deferred scope\n- Reminder system\n"
    # The once-per-run flags and the revision count do not hide a finding that is still there.
    state = _state(specification_deferrals_checked=True, architecture_revision_count=5)
    assert workflow._the_harness_findings_still_open(state, settled, ["deferrals"]) == []
    assert len(workflow._the_harness_findings_still_open(state, still, ["deferrals"])) == 1
    assert workflow._the_harness_findings_still_open(state, still, ["no-such-check"]) == []


def test_the_node_records_what_overturned_an_approval_and_rechecks_it_behind_the_switch():
    source = inspect.getsource(workflow)
    assert 'update["approved_but_for_the_harness"] = fired if reviewer_approved and fired else []' in source
    assert "settled = _approved_once_the_harness_s_findings_are_settled(state, spec_text)" in source
    for name in ("coverage", "deferrals", "contract", "kept"):
        assert f'fired.append("{name}")' in source


def test_off_in_code_and_registered():
    assert workflow.harness_findings_rechecked.ON_BY_DEFAULT is False
    assert "HARNESS_FINDINGS_RECHECKED" in provenance.SWITCHES
    assert "HARNESS_FINDINGS_RECHECKED" in switches.GROUPS["Efficiency"]
    assert "approved_but_for_the_harness" in workflow.WorkflowGraphState.__annotations__


def test_a_settled_revision_is_approved_and_an_unsettled_one_reviewed(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_FINDINGS_RECHECKED", "on")
    monkeypatch.setattr(workflow, "_record_document", lambda *a, **k: None)
    monkeypatch.setattr(workflow, "_review_enabled", lambda state, point: False)
    state = _state(approved_but_for_the_harness=["deferrals"], repository=SimpleNamespace(root_path=str(tmp_path)),
                   decisions=[])
    approved = workflow._approved_once_the_harness_s_findings_are_settled(
        state, "## Features\n- Notes carry tags, due dates and reminders.\n")
    assert approved["stage"] == "scaffold" and approved["architecture_review"].status == "approved"
    assert workflow._approved_once_the_harness_s_findings_are_settled(state, "## Deferred scope\n- Reminder system\n") is None
    monkeypatch.setenv("HARNESS_FINDINGS_RECHECKED", "off")
    assert workflow._approved_once_the_harness_s_findings_are_settled(
        state, "## Features\n- Notes carry tags, due dates and reminders.\n") is None
