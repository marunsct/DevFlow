"""A parallel worker that paused must be *resumed*, on its own thread.

Driven through the compiled graph, because the two unit-level fixes before this
one were each proven only against a state the worker never sees.

9458457 stopped siblings resuming the paused worker's thread - one gated call
had been executing once per concurrent branch, 657 extra executions across 18
runs. It decided who owned the pause by reading `stage`. But a parallel resume
enters `specialist_dispatch`, which returns `stage: specialist_dispatch_parallel`
before the router fans out, so by the time any worker runs the
`awaiting_approval:<name>` marker is gone. No worker matched, the decision was
taken from all of them including its owner, and on one run
`specialist_backend_1` started over at least six times - the same `ls`, the
same three document reads, "I'll create app.js", the gated write, the pause -
without writing a byte.

The unit tests passed because they built the state with the marker in it. The
graph tests passed because the scripted agent cannot tell a resume from a fresh
start: either way it pops its next response. So these record the one thing that
distinguishes them - whether the agent was handed a `Command` or a new request,
and on which thread.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from langgraph.types import Command

from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.graph.workflow import resume_pending_approval, start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _FakeAgent,
    _approved_review,
    _document,
    _graph,
    _milestone_review,
    _repository,
    _script_through_architecture,
    _security_review,
    _specialist,
    _sprint_plan,
    agents,
    approve_write_decision,
    pause_for_approval,
    responds_with,
)


@pytest.fixture
def parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    real = config.load_settings()
    monkeypatch.setattr(
        config,
        "load_settings",
        lambda *args, **kwargs: dataclasses.replace(real, execution_mode="parallel"),
    )


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Every agent invocation, in order: (role, "resume" | "fresh", thread_id)."""
    seen: list[tuple[str, str, str]] = []
    original = _FakeAgent.invoke

    def recording(self: _FakeAgent, payload: Any, config: Any = None) -> dict[str, Any]:
        thread = str(((config or {}).get("configurable") or {}).get("thread_id") or "")
        kind = "resume" if isinstance(payload, Command) else "fresh"
        seen.append((self.role, kind, thread))
        return original(self, payload, config)

    monkeypatch.setattr(_FakeAgent, "invoke", recording)
    return seen


def _plan(*tasks: tuple[str, str]) -> MilestonePlanOutput:
    return MilestonePlanOutput(
        selected_sprint_goal="Sprint 1: booking",
        delegated_tasks=[
            SpecialistTask(specialist_role=role, task_description=text, acceptance_criteria=["works"])
            for role, text in tasks
        ],
        review_task_assignments=["change -> task 1"],
    )


def _script(agents: ScriptedAgents, plan: MilestonePlanOutput) -> None:
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(plan)])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])


def _of(calls: list[tuple[str, str, str]], role: str) -> list[tuple[str, str]]:
    return [(kind, thread) for who, kind, thread in calls if who == f"specialist_{role}"]


def _finish(graph: Any, state: dict, thread: str, limit: int = 6) -> dict:
    """Answer every approval the way `auto_approve` does, until the run stops pausing."""
    for _ in range(limit):
        if not str(state.get("stage", "")).startswith("awaiting_approval:"):
            return state
        state = resume_pending_approval(graph, thread, approve_write_decision())
    return state


class TestTheOwnerResumes:
    def test_the_paused_worker_is_resumed_on_the_thread_it_paused_on(
        self, agents: ScriptedAgents, parallel: None, calls: list, tmp_path: Any
    ) -> None:
        """The one run livelock, as one assertion."""
        _script(agents, _plan(("backend", "Create api.py."), ("database", "Create schema.sql.")))
        agents.script("specialist_backend", [
            pause_for_approval("api.py", "Backend write"),
            responds_with(_specialist()),
        ])
        agents.script("specialist_database", [responds_with(_specialist())])
        agents.script("specialist_testing", [responds_with(_specialist())])
        graph = _graph()

        state = start_workflow(graph, _document(), _repository(tmp_path), "run-own-thread")
        assert state["stage"] == "awaiting_approval:specialist_backend_0"
        state = resume_pending_approval(graph, "run-own-thread", approve_write_decision())

        backend = _of(calls, "backend")
        assert backend[0][0] == "fresh"
        assert backend[1] == ("resume", backend[0][1]), (
            f"the decision must resume the thread that paused, got {backend[1]}"
        )
        assert len(backend) == 2, "a worker that restarts instead of resuming is invoked again and again"
        assert state["stage"] == "complete", state.get("error")

    def test_nobody_else_resumes_that_thread(
        self, agents: ScriptedAgents, parallel: None, calls: list, tmp_path: Any
    ) -> None:
        """The triplication: one gated call executed once per concurrent branch."""
        _script(agents, _plan(("backend", "Create api.py."), ("database", "Create schema.sql.")))
        agents.script("specialist_backend", [
            pause_for_approval("api.py", "Backend write"),
            responds_with(_specialist()),
        ])
        agents.script("specialist_database", [
            pause_for_approval("schema.sql", "Schema write"),
            responds_with(_specialist()),
        ])
        agents.script("specialist_testing", [responds_with(_specialist())])
        graph = _graph()

        state = start_workflow(graph, _document(), _repository(tmp_path), "run-two-pauses")
        state = _finish(graph, state, "run-two-pauses")

        assert state["stage"] == "complete", state.get("error")
        for role in ("backend", "database"):
            mine = _of(calls, role)
            first_thread = mine[0][1]
            resumes = [thread for kind, thread in mine if kind == "resume"]
            assert resumes == [first_thread], f"{role} must resume exactly once, on its own thread: {mine}"
            others = [
                (who, thread) for who, kind, thread in calls
                if kind == "resume" and thread == first_thread and who != f"specialist_{role}"
            ]
            assert not others, f"{role}'s thread was resumed by another role: {others}"

    def test_a_pause_queued_behind_another_costs_no_model_call(
        self, agents: ScriptedAgents, parallel: None, calls: list, tmp_path: Any
    ) -> None:
        """Two workers pause together; the second waits its turn without re-running."""
        _script(agents, _plan(("backend", "Create api.py."), ("database", "Create schema.sql.")))
        agents.script("specialist_backend", [
            pause_for_approval("api.py", "Backend write"),
            responds_with(_specialist()),
        ])
        agents.script("specialist_database", [
            pause_for_approval("schema.sql", "Schema write"),
            responds_with(_specialist()),
        ])
        agents.script("specialist_testing", [responds_with(_specialist())])
        graph = _graph()

        state = start_workflow(graph, _document(), _repository(tmp_path), "run-queued")
        _finish(graph, state, "run-queued")

        # Its first invocation and its one resume - never a fresh restart while
        # it waited behind the backend's gate.
        assert [kind for kind, _ in _of(calls, "database")] == ["fresh", "resume"]


class TestAHeldBackTaskStillRuns:
    """Two tasks naming one file are staggered, and the second must still run."""

    SHARED = (("backend", "Create app.js with the pure functions."),
              ("testing", "Write app.test.js covering the functions in app.js."))

    def test_the_deferred_task_runs_after_the_first_finishes(
        self, agents: ScriptedAgents, parallel: None, calls: list, tmp_path: Any
    ) -> None:
        """Before, gather handed on to the tests with the deferred task never sent.

        It only ran because the resume path used to send every pending task at
        the first approval - which was also what switched the staggering off.
        """
        _script(agents, _plan(*self.SHARED))
        agents.script("specialist_backend", [responds_with(_specialist())])
        # The delegated task, then the verification round.
        agents.script("specialist_testing", [responds_with(_specialist())] * 2)
        graph = _graph()

        state = start_workflow(graph, _document(), _repository(tmp_path), "run-deferred")

        assert state["stage"] == "complete", state.get("error")
        assert "specialist_testing_1" in state["specialist_outputs"], (
            "the task held back for sharing app.js was never dispatched"
        )

    def test_a_resume_does_not_release_it_early(
        self, agents: ScriptedAgents, parallel: None, calls: list, tmp_path: Any
    ) -> None:
        """One run: the first approval dispatched `testing` onto `app.js`
        while `backend` was still writing it.

        Checked at a superstep boundary rather than by call order. Two workers
        dispatched together still land in a list one after the other, so an
        ordering assertion passes on exactly the code it is meant to catch - it
        did, the first time this was written. Here `backend` pauses twice, and
        the question is asked while it sits at its second gate: by then the old
        resume path had already sent `testing` out beside it.
        """
        _script(agents, _plan(*self.SHARED))
        agents.script("specialist_backend", [
            pause_for_approval("app.js", "Backend write"),
            pause_for_approval("app.js", "Backend second write"),
            responds_with(_specialist()),
        ])
        agents.script("specialist_testing", [responds_with(_specialist())] * 2)
        graph = _graph()

        state = start_workflow(graph, _document(), _repository(tmp_path), "run-not-early")
        assert _of(calls, "testing") == [], "held back while backend holds app.js"

        state = resume_pending_approval(graph, "run-not-early", approve_write_decision())
        assert state["stage"] == "awaiting_approval:specialist_backend_0"
        assert _of(calls, "testing") == [], (
            "released by the first approval while backend still holds app.js"
        )

        state = _finish(graph, state, "run-not-early")
        assert state["stage"] == "complete", state.get("error")
        assert "specialist_testing_1" in state["specialist_outputs"]


class TestIndependentTasksStillRunTogether:
    def test_two_tasks_with_different_files_both_go_at_once(
        self, agents: ScriptedAgents, parallel: None, calls: list, tmp_path: Any
    ) -> None:
        _script(agents, _plan(("backend", "Create api.py."), ("database", "Create schema.sql.")))
        agents.script("specialist_backend", [
            pause_for_approval("api.py", "Backend write"),
            responds_with(_specialist()),
        ])
        agents.script("specialist_database", [responds_with(_specialist())])
        agents.script("specialist_testing", [responds_with(_specialist())])
        graph = _graph()

        start_workflow(graph, _document(), _repository(tmp_path), "run-together")

        # Both dispatched in the first fan-out, before anyone answered anything.
        assert len(_of(calls, "database")) == 1
        assert len(_of(calls, "backend")) == 1
