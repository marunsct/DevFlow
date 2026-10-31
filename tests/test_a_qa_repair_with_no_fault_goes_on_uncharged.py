"""The whole path, dispute to lock: a repair whose QA finds no fault in the test locks again unreviewed and uncharged.

Behind `QA_SAYS_THE_PRODUCT_IS_AT_FAULT`. Named by the switch alone, so this reads the behaviour on code without it.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.acceptance import junit, suite
from app.acceptance.criteria import Criterion
from app.graph import acceptance_nodes, workflow

_TEST = "[AC-1] saving answers 201"
_STANDARD = "saving a record answers 201 with the record"
_FAILURE = "Expected: 201 Received: 500"
_CLAIM = f'PRODUCT_AT_FAULT: {_TEST}: the standard says "{_STANDARD}"; the run shows "{_FAILURE}"'
_CTX = SimpleNamespace(model=None, judgement_model=None, checkpointer=None, repo_root=None, allow_subdirectories=True)


@pytest.fixture
def state(monkeypatch, tmp_path):
    monkeypatch.setenv("QA_SAYS_THE_PRODUCT_IS_AT_FAULT", "on")
    spec = tmp_path / "acceptance" / "api.spec.js"
    spec.parent.mkdir()
    spec.write_text(f"test('{_TEST}', async () => {{}});\n")
    monkeypatch.setattr(suite, "suite_files", lambda _root: [spec])
    suite.save_criteria(str(tmp_path), [Criterion(id="AC-1", text=_STANDARD, source="brief")])
    suite.lock(str(tmp_path))
    measured = suite.AcceptanceResult(ran=True, exit_code=1, command="npm test", report=junit.Report(found=True, tests=[
        junit.TestResult(name=_TEST, outcome="failed", message=f"Error: {_FAILURE}"),
    ]))
    monkeypatch.setattr(suite, "run", lambda _root: measured)
    for check in ("gaps", "tests_that_cannot_pass", "tests_that_want_json_from_a_204", "vacuous_green", "locators_nobody_sees",
                  "tests_whose_success_status_the_contract_does_not_give", "locators_that_pick_one", "controls_never_found_by_name"):
        monkeypatch.setattr(suite, check, lambda *_a, **_k: [])
    monkeypatch.setattr(acceptance_nodes, "_decide", lambda *_a, **_k: None)
    monkeypatch.setattr(acceptance_nodes, "_stack", lambda _state: None)
    monkeypatch.setattr(acceptance_nodes, "_the_testability_advice", lambda _state: [])
    monkeypatch.setattr(acceptance_nodes.acceptance_requests, "build_author_request", lambda *_a, **_k: {"messages": []})
    monkeypatch.setattr("app.agents.specialists.create_specialist_agent", lambda *_a, **_k: None)
    monkeypatch.setattr("app.agents.acceptance_reviewer.create_acceptance_reviewer_agent", lambda *_a, **_k: None)
    monkeypatch.setattr(workflow, "_record_document", lambda *_a, **_k: None)
    return {"repository": SimpleNamespace(root_path=str(tmp_path)), "suite_repairs": 1,
            "suite_repaired_tests": ["earlier"], "suite_reclassified_tests": []}


def _through_qa(monkeypatch, state, blockers) -> tuple[dict, list[str]]:
    """Reopen as a dispute, QA answers `blockers`, the review runs: (its update, the stages that called a model)."""
    called: list[str] = []

    def agent(_state, _config, *, stage_name, output_key, **_kwargs):
        called.append(stage_name)
        if output_key == "__acceptance_author__":
            return {"__acceptance_author__": SimpleNamespace(blockers=blockers), "stage": "acceptance_review"}
        return {"__acceptance_review__": SimpleNamespace(approved=True, findings=[]), "stage": "acceptance_review"}

    monkeypatch.setattr(workflow, "_run_gated_agent", agent)
    reopened = acceptance_nodes.reopen_the_suite_for(
        state, [f"`{_TEST}` cannot pass: a reason here"], return_to=acceptance_nodes.SPRINT_REPLAN, reclassifying=True)
    assert reopened["suite_repairs"] == 2 and _TEST in reopened["suite_reclassified_tests"]
    now = {**state, **reopened}
    now = {**now, **acceptance_nodes.acceptance_author(now, {}, _CTX)}
    called.clear()
    return acceptance_nodes.acceptance_review(now, {}, _CTX), called


def test_no_fault_found_locks_unreviewed_and_uncharged(monkeypatch, state):
    update, called = _through_qa(monkeypatch, state, [_CLAIM])
    assert called == []
    assert update["suite_repairs"] == 1 and update["suite_repaired_tests"] == ["earlier"]
    assert update["suite_reclassified_tests"] == []
    assert update["stage"] == "technical_lead"
    assert suite.is_locked(state["repository"].root_path)


def test_a_claim_with_no_evidence_is_reviewed_and_stays_charged(monkeypatch, state):
    update, called = _through_qa(monkeypatch, state, [f"PRODUCT_AT_FAULT: {_TEST}"])
    assert called == ["acceptance_review_1"]
    assert "suite_repairs" not in update
