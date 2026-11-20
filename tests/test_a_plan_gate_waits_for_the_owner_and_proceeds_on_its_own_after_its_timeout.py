"""The plan gate (plan WS.3): the sprint plan waits for the owner's go, takes a direction, and goes on by itself.

Before, the owner could stop a run at the specification or after a sprint, but not at the plan: the sprints were
split and the first was built before anyone could say "build sign-in first". A gate that waits for ever is no better
for an owner who walked away, so this one goes on by itself after its time, and says it did.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _document,
    _graph,
    _repository,
    _script_through_architecture,
    _script_through_sprint,
    _sprint_plan,
    agents,
    responds_with,
)

from app.graph.plan_gate import the_owners_direction
from app.graph.workflow import approve_decision, request_changes_decision, resume_pending_review, start_workflow
from app.observability.transcript import read_transcript
from app.server import approval_timeouts
from app.state import ReviewRequestStatus

PLAN_GATE = {"sprint_plan": True}
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def _at_the_plan_gate(agents: ScriptedAgents, tmp_path: Any, thread: str) -> tuple[Any, dict[str, Any]]:
    graph = _graph()
    _script_through_architecture(agents, _approved_review())
    _script_through_sprint(agents)
    state = start_workflow(graph, _document(), _repository(tmp_path), thread, review_policy=PLAN_GATE)
    return graph, state


def test_with_the_plan_gate_on_the_run_waits_after_the_plan_before_any_sprint_is_built(agents, tmp_path):
    _graph_, state = _at_the_plan_gate(agents, tmp_path, "run-plan-gate")

    assert state["stage"] == "awaiting_user_review:sprint_plan"
    assert state["pending_review"].status is ReviewRequestStatus.PENDING
    assert len(agents.requests["scrum_master"]) == 1
    assert agents.requests["technical_lead"] == []


def test_a_go_at_the_plan_gate_builds_the_plan(agents, tmp_path):
    graph, _state = _at_the_plan_gate(agents, tmp_path, "run-plan-go")

    state = resume_pending_review(graph, "run-plan-go", approve_decision())

    assert state["stage"] == "complete", state.get("error")
    assert state["reviews"]["sprint_plan"].status is ReviewRequestStatus.APPROVED
    assert len(agents.requests["technical_lead"]) == 1


def test_a_direction_at_the_plan_gate_reaches_the_scrum_master_who_plans_again(agents, tmp_path):
    graph, _state = _at_the_plan_gate(agents, tmp_path, "run-plan-steer")
    agents.scripts["scrum_master"] = [responds_with(_sprint_plan())]

    state = resume_pending_review(graph, "run-plan-steer", request_changes_decision("Build sign-in first."))

    assert state["stage"] == "awaiting_user_review:sprint_plan"
    assert state["reviews"]["sprint_plan"].revision == 2
    replan = agents.last_request_text("scrum_master")
    assert "Build sign-in first." in replan
    assert "Sprint 1: booking" in replan  # the plan the owner read
    assert agents.requests["technical_lead"] == []


def test_a_plan_gate_answered_by_its_time_is_recorded_as_going_on_by_itself(agents, tmp_path):
    graph, _state = _at_the_plan_gate(agents, tmp_path, "run-plan-timeout")

    state = resume_pending_review(graph, "run-plan-timeout", approve_decision("No answer.", by_timeout=True))

    decision = [d for d in state["decisions"] if d["point"] == "sprint_plan"][-1]  # after the plan's own record
    assert decision["decided_by"] == "timeout"
    assert state["stage"] == "complete", state.get("error")


def _waiting(run_id: str, stage: str, minutes: int | None, waited: float) -> SimpleNamespace:
    return SimpleNamespace(run_id=run_id, status="waiting_for_review", current_stage=stage,
                           approval_timeout_minutes=minutes, updated_at=(NOW - timedelta(minutes=waited)).isoformat())


def test_a_run_left_at_the_plan_gate_goes_on_after_fifteen_minutes_and_another_review_still_waits():
    runs = [
        _waiting("plan-16", "awaiting_user_review:sprint_plan", None, 16),
        _waiting("plan-14", "awaiting_user_review:sprint_plan", None, 14),
        _waiting("spec-999", "awaiting_user_review:technical_specification", None, 999),
        _waiting("plan-own-60", "awaiting_user_review:sprint_plan", 60, 30),
    ]

    assert approval_timeouts.due(runs, NOW) == [("plan-16", "review", 15)]


def test_the_plan_gate_s_time_is_configurable(monkeypatch):
    monkeypatch.setenv("PLAN_GATE_MINUTES", "3")

    assert approval_timeouts.due([_waiting("p", "awaiting_user_review:sprint_plan", None, 4)], NOW) == [("p", "review", 3)]


def test_the_sweep_answers_the_plan_gate_as_its_time_and_says_so_on_the_transcript_and_the_stream(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    run = _waiting("run-swept", "awaiting_user_review:sprint_plan", None, 20)
    decisions: list[dict[str, Any]] = []
    published: list[Any] = []

    class _Bus:
        async def next_sequence(self, run_id):
            return 7

        async def publish(self, run_id, event):
            published.append(event)

    class _Runner:
        run_store = SimpleNamespace(list_all=lambda limit, offset: [run])
        event_bus = _Bus()

        async def submit_review(self, run_id, decision):
            decisions.append(decision)

    assert asyncio.run(approval_timeouts.approve_what_is_due(_Runner(), NOW)) == ["run-swept"]

    assert decisions[0]["type"] == "approve" and decisions[0]["decided_by"] == "timeout"
    [gate] = read_transcript("run-swept", {"gate"})
    assert (gate["event"], gate["minutes"]) == ("proceeded_on_its_own", 15)
    [event] = published
    assert event.event_type == "review_decision" and event.metadata["decided_by"] == "timeout"
    assert event.stage == "sprint_plan"


BANNED = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.IGNORECASE)


def test_what_the_scrum_master_is_told_at_the_plan_gate_has_none_of_the_banned_words():
    text = the_owners_direction(["Build sign-in first."], '{"sprints": []}')

    assert "Build sign-in first." in text
    assert not BANNED.search(text.replace("Build sign-in first.", ""))


def test_the_open_plan_gate_says_when_the_run_goes_on_by_itself(client, tmp_path):
    from app.server.run_store import RunStore

    response = client.post("/api/runs", files=[("files", ("brief.md", b"# A small service", "text/markdown"))])
    run_id = response.json()["run_id"]
    store = RunStore()
    record = store.load(run_id)
    record.status, record.current_stage = "waiting_for_review", "awaiting_user_review:sprint_plan"
    record.repo_root, record.updated_at = str(tmp_path), "2026-11-20T12:00:00+00:00"
    store.save(record)

    review = client.get(f"/api/runs/{run_id}/review").json()["review"]

    assert review["proceeds_at"] == "2026-11-20T12:15:00+00:00"
