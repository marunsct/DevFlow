"""Shipping: the release gate, change requests, review evidence and the decision log."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.acceptance import junit, suite
from app.acceptance.criteria import number
from app.decisions import record_decision, render
from app.graph import delivery

BRIEF = "# Brief\n## Features\n- Add a note\n- Delete a note\n"
CONFIG = {"configurable": {"thread_id": "t"}}


def _state(root: Path, **extra: Any) -> dict[str, Any]:
    (root / ".project-directory").write_text("notes\n")
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "product_intake": SimpleNamespace(product_name="Notes"),
        "sprint_plan": SimpleNamespace(sprints=[SimpleNamespace(goal="Notes", criteria=[])]),
        **extra,
    }


@pytest.fixture(autouse=True)
def _no_cancel(monkeypatch):
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)


def _locked_suite(root: Path) -> None:
    suite.save_criteria(root, number(BRIEF))
    target = root / "notes" / "acceptance" / "notes.spec.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("test('[AC-1] adds', ()=>{});\ntest('[AC-2] deletes', ()=>{});\n")
    suite.lock(root)


def _result(root: Path, failed: tuple[str, ...] = ()) -> suite.AcceptanceResult:
    report = junit.Report(found=True, tests=[
        junit.TestResult(name="[AC-1] adds", outcome="failed" if "AC-1" in failed else "passed", message="no"),
        junit.TestResult(name="[AC-2] deletes", outcome="failed" if "AC-2" in failed else "passed", message="no"),
    ])
    return suite._judged(root, suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=report), True)


def test_a_release_with_every_criterion_passing_completes(tmp_path, monkeypatch) -> None:
    _locked_suite(tmp_path)
    monkeypatch.setattr(suite, "run", lambda root: _result(tmp_path))

    update = delivery.release(_state(tmp_path), CONFIG, None)

    assert update["stage"] == "complete"
    assert update["decisions"][-1]["decision"] == "release"
    page = (tmp_path / "docs" / "reviews" / "release-evidence.md").read_text()
    assert "| AC-2 | Delete a note | PASSED |" in page


def test_the_release_review_is_offered_in_approval_mode(tmp_path, monkeypatch) -> None:
    _locked_suite(tmp_path)
    monkeypatch.setattr(suite, "run", lambda root: _result(tmp_path))
    state = _state(tmp_path, review_policy={delivery.RELEASE_REVIEW: True})
    assert delivery.release(state, CONFIG, None)["stage"] == "user_review_release"


def test_a_failing_criterion_holds_the_release_then_escalates(tmp_path, monkeypatch) -> None:
    _locked_suite(tmp_path)
    monkeypatch.setattr(suite, "run", lambda root: _result(tmp_path, failed=("AC-2",)))

    held = delivery.release(_state(tmp_path), CONFIG, None)
    assert held["stage"] == "technical_lead" and held["release_attempts"] == 1
    assert "AC-2" in held["revision_comments"][-1]

    escalated = delivery.release(
        _state(tmp_path, release_attempts=delivery.MAX_RELEASE_ATTEMPTS), CONFIG, None
    )
    assert escalated["stage"] == "escalation" and "AC-2" in escalated["escalation"]["error"]


def test_a_run_without_a_suite_releases_on_its_reviews(tmp_path) -> None:
    update = delivery.release(_state(tmp_path), CONFIG, None)
    assert update["stage"] == "complete"


def test_a_requested_change_becomes_a_change_request_qa_proves(tmp_path) -> None:
    _locked_suite(tmp_path)
    state = _state(tmp_path, revision_comments=["Show the newest note first"])

    update = delivery.change_request(state, CONFIG, None)

    assert update["stage"] == "acceptance_author"
    assert update["acceptance_return_to"] == "technical_lead"
    assert suite.change_requests(tmp_path) == {"CR-1": "Show the newest note first"}
    decision = update["decisions"][-1]
    assert decision["decided_by"] == "user" and decision["affects"] == ["CR-1"]
    # Once QA has written its test, the lead is told what must now pass.
    brief = delivery.change_request_brief(str(tmp_path))
    assert brief and "CR-1" in brief[0] and "Show the newest note first" in brief[0]


def test_without_a_suite_a_requested_change_goes_to_the_lead(tmp_path) -> None:
    update = delivery.change_request(_state(tmp_path, revision_comments=["Bigger buttons"]), CONFIG, None)
    assert update["stage"] == "technical_lead" and update["revision_comments"] == ["Bigger buttons"]


def test_the_acceptance_stages_return_a_change_request_to_the_sprint(tmp_path, monkeypatch) -> None:
    from app.graph import acceptance_nodes

    _locked_suite(tmp_path)
    suite.add_change_request(tmp_path, "Newest first")
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    suite.unlock(tmp_path)
    spec.write_text(spec.read_text() + "test('[CR-1] newest first', ()=>{});\n")
    monkeypatch.setattr(suite, "run", lambda root: _result(tmp_path))

    def gated(state, config, **kwargs):
        return {kwargs["output_key"]: SimpleNamespace(approved=True, findings=[]), "stage": "x"}

    monkeypatch.setattr("app.graph.workflow._run_gated_agent", gated)
    monkeypatch.setattr("app.agents.acceptance_reviewer.create_acceptance_reviewer_agent", lambda *a, **k: object())
    state = _state(tmp_path, acceptance_round=1, acceptance_return_to="technical_lead")
    state["document"] = SimpleNamespace(text=BRIEF)

    update = acceptance_nodes.acceptance_review(state, CONFIG, acceptance_nodes.Context(None, None, None, None))

    assert update["stage"] == "technical_lead" and update["acceptance_return_to"] is None
    assert any("CR-1" in line for line in update["revision_comments"])


def test_the_evidence_page_shows_what_a_reviewer_needs(tmp_path) -> None:
    _locked_suite(tmp_path)
    _result(tmp_path, failed=("AC-2",))
    state = _state(tmp_path)
    record_decision(state, state, point="stack", question="What is it built with?", decision="JS", rationale="r")

    page = delivery.evidence(state, 1, "Notes")

    assert "| AC-1 | Add a note | PASSED |" in page and "| AC-2 | Delete a note | FAILED |" in page
    assert "DR-1" in page and "What is it built with?" in page


def test_decision_records_number_themselves_and_render() -> None:
    state: dict[str, Any] = {}
    update: dict[str, Any] = {}
    record_decision(state, update, point="stack", question="Q1", decision="a", rationale="r1")
    record_decision(state, update, point="sprint", question="Q2", decision="b", rationale="r2", decided_by="user", comment="c")
    assert [d["id"] for d in update["decisions"]] == ["DR-1", "DR-2"]
    text = render(update["decisions"])
    assert "## DR-2: Q2" in text and "user" in text and "**Comment:** c" in text


def test_a_review_gate_records_the_person_s_decision() -> None:
    from app.graph.workflow import _run_review_gate
    from app.review import start_review

    review = start_review(run_id="r", thread_id="r", stage="validation", artifact_id="acceptance-tests", reviewer="me")
    state = {
        "reviews": {"acceptance_tests": review},
        "pending_review_decision": {"type": "request_changes", "comment": "AC-2 needs a reload check"},
    }
    update = _run_review_gate(
        state, CONFIG, review_point="acceptance_tests", artifact_id="acceptance-tests",
        approved_next="scrum_master", changes_next="acceptance_author",
    )
    assert update["stage"] == "acceptance_author"
    decision = update["decisions"][-1]
    assert decision["decided_by"] == "user" and decision["decision"] == "request changes"
    assert decision["comment"] == "AC-2 needs a reload check"


def test_the_api_serves_decisions_and_evidence(client, monkeypatch) -> None:
    response = client.post(
        "/api/runs", files=[("files", ("brief.md", io.BytesIO(b"# Brief"), "text/markdown"))]
    )
    run_id = response.json()["run_id"]
    client.post(f"/api/runs/{run_id}/start", json={"workspace_label": "delivery"})
    from app.server.run_store import RunStore
    from app.server.runner import RunRecord

    workspace = Path(RunStore.shared().load(run_id).repo_root)
    _locked_suite(workspace)
    _result(workspace)
    monkeypatch.setattr(
        RunRecord, "graph_state",
        lambda self, checkpointer=None: {"decisions": [{"id": "DR-1", "question": "Q", "decision": "d"}]},
    )

    decisions = client.get(f"/api/runs/{run_id}/decisions").json()["decisions"]
    evidence = client.get(f"/api/runs/{run_id}/evidence").json()

    assert decisions[0]["id"] == "DR-1"
    assert evidence["acceptance"]["criteria"]["AC-1"]["status"] == "passed"
