"""Under auto-approve, every queued parallel pause is answered in one resume.

A fan-out's workers each pause at their first gated call. `specialist_gather`
surfaces one pause per superstep, so only the surfaced worker moved: the others
were re-sent, found no decision, and handed their pause straight back. Measured
on one run: more than one model call was in flight for 13-28% of the
specialists' time, and the model server's other parallel slots sat idle.

So under auto-approve the runner decides every queued pause with the surfaced
one - each through its own stage's gate budget and loop check - and each
worker resumes its own paused thread with its own decision. Linear mode and an
attended run never have a queued pause, so nothing changes for them.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.graph.workflow import (
    APPROVAL_PAUSE_PREFIX,
    _QUEUED_AT,
    _as_a_queued_pause,
    _only_this_worker_s_pause,
    queued_parallel_pauses,
    resume_pending_approval,
)

SURFACED, QUEUED = "specialist_ui_ux_0", "specialist_backend_1"
APPROVE = {"type": "approve"}


def _state(**over):
    state = {
        "stage": f"{APPROVAL_PAUSE_PREFIX}{SURFACED}",
        "pending_inner_thread_id": f"t:{SURFACED}",
        "pending_approval": {"tool": "write_artifact"},
        "specialist_pauses": {
            SURFACED: None,
            QUEUED: {"pending_inner_thread_id": f"t:{QUEUED}", "pending_approval": {"tool": "edit_artifact"}, _QUEUED_AT: 5.0},
        },
    }
    state.update(over)
    return state


class TestTheGraphSide:
    def test_a_queued_worker_with_a_decision_resumes_its_own_thread(self) -> None:
        override = _only_this_worker_s_pause(_state(queued_decisions={QUEUED: APPROVE}), QUEUED)

        assert override["pending_decision"] == APPROVE
        assert override["pending_inner_thread_id"] == f"t:{QUEUED}"
        assert override["pending_approval"] == {"tool": "edit_artifact"}

    def test_without_one_it_hands_its_pause_back_as_before(self) -> None:
        override = _only_this_worker_s_pause(_state(), QUEUED)

        assert override["pending_decision"] is None
        assert override["pending_inner_thread_id"] == f"t:{QUEUED}"

    def test_a_decision_for_another_stage_is_not_taken(self) -> None:
        override = _only_this_worker_s_pause(_state(queued_decisions={"specialist_testing_2": APPROVE}), QUEUED)

        assert override["pending_decision"] is None

    def test_the_surfaced_worker_is_untouched(self) -> None:
        assert _only_this_worker_s_pause(_state(queued_decisions={QUEUED: APPROVE}), SURFACED) == {}

    def test_the_queue_the_runner_reads_leaves_out_the_surfaced_pause(self) -> None:
        assert queued_parallel_pauses(_state()) == {
            QUEUED: {"pending_approval": {"tool": "edit_artifact"}, "pending_inner_thread_id": f"t:{QUEUED}", "queued_at": 5.0}
        }
        assert queued_parallel_pauses({"stage": f"{APPROVAL_PAUSE_PREFIX}test_round_0"}) == {}

    def test_a_pause_after_a_batch_answer_joins_the_back(self) -> None:
        entry = _as_a_queued_pause(_state(), QUEUED, {"pending_inner_thread_id": f"t:{QUEUED}"}, answered=True)

        assert entry[_QUEUED_AT] > 1_000_000_000

    def test_the_resume_carries_the_queued_decisions(self) -> None:
        sent = []
        graph = SimpleNamespace(invoke=lambda update, config=None: sent.append(update) or {"stage": "complete"})

        resume_pending_approval(graph, "thread-1", APPROVE, queued_decisions={QUEUED: APPROVE})
        resume_pending_approval(graph, "thread-1", APPROVE)

        assert sent == [{"pending_decision": APPROVE, "queued_decisions": {QUEUED: APPROVE}}, {"pending_decision": APPROVE}]


class TestTheCount:
    def _approval(self, path="app/a.js", notes="x", kind="write"):
        return SimpleNamespace(artifact_path=path, notes=notes, action_kind=kind)

    def test_a_read_does_not_spend_the_budget(self) -> None:
        from app.server.runner import _GateCount

        count = _GateCount()
        count.observe(self._approval(kind="read"))
        count.observe(self._approval(notes="y"))

        assert count.gates == 1

    def test_an_identical_write_repeated_is_denied_then_fails(self) -> None:
        from app.server.runner import MAX_IDENTICAL_GATES, MAX_LOOPS_ANSWERED_BY_DENIAL, _GateCount

        count, verdicts = _GateCount(), []
        for _ in range((MAX_IDENTICAL_GATES + 1) * (MAX_LOOPS_ANSWERED_BY_DENIAL + 1)):
            verdict, _ = count.observe(self._approval())
            verdicts.append(verdict)
            if verdict == "fail":
                break

        assert verdicts.count("deny") == MAX_LOOPS_ANSWERED_BY_DENIAL
        assert verdicts[-1] == "fail"


def _approval(path: str, notes: str = "write"):
    return SimpleNamespace(artifact_path=path, notes=notes, action_kind="write", tool_name="write_artifact")


class _RecordingGraph:
    def __init__(self, states):
        self._states = list(states)
        self.inputs: list[dict] = []

    def invoke(self, update, config=None):
        self.inputs.append(update)
        return self._states.pop(0) if self._states else {"stage": "complete"}


def _paused(surfaced: str, queued: dict[str, tuple[str, float]]):
    return {
        "stage": f"{APPROVAL_PAUSE_PREFIX}{surfaced}",
        "pending_approval": _approval(f"app/{surfaced}.js"),
        "pending_inner_thread_id": f"t:{surfaced}",
        "specialist_pauses": {
            surfaced: None,
            **{stage: {"pending_approval": _approval(path), "pending_inner_thread_id": f"t:{stage}", _QUEUED_AT: at}
               for stage, (path, at) in queued.items()},
        },
    }


class TestTheRunnerSide:
    @pytest.fixture
    def runner(self, run_store, redis_container, monkeypatch):
        from app.server.events import EventBus
        from app.server.redis_client import reset_clients
        from app.server.runner import WorkflowRunner

        reset_clients()
        monkeypatch.setenv("CHECKPOINTER_TYPE", "memory")
        return WorkflowRunner(EventBus(), run_store=run_store)

    def _record(self, runner, **over):
        record = runner.register_run(
            run_id="run-1", thread_id="thread-run-1", document_names=["brief.md"],
            document_paths=["/tmp/brief.md"], owner="alice", tenant_id="acme",
        )
        for key, value in over.items():
            setattr(record, key, value)
        runner.run_store.save(record)
        return record

    async def test_every_queued_pause_is_answered_in_the_same_resume(self, runner) -> None:
        record = self._record(runner, auto_approve=True)
        graph = _RecordingGraph([])

        await runner._handle_state(record, graph, _paused(SURFACED, {QUEUED: ("app/b.js", 5.0)}), {})

        assert graph.inputs[0]["pending_decision"]["type"] == "approve"
        assert set(graph.inputs[0]["queued_decisions"]) == {QUEUED}
        assert runner.run_store.load("run-1").status == "completed"

    async def test_a_lone_pause_resumes_exactly_as_before(self, runner) -> None:
        record = self._record(runner, auto_approve=True)
        graph = _RecordingGraph([])

        await runner._handle_state(record, graph, _paused(SURFACED, {}), {})

        assert "queued_decisions" not in graph.inputs[0]

    async def test_an_attended_run_still_waits_for_a_person(self, runner) -> None:
        record = self._record(runner, auto_approve=False)
        graph = _RecordingGraph([])

        await runner._handle_state(record, graph, _paused(SURFACED, {QUEUED: ("app/b.js", 5.0)}), {})

        assert graph.inputs == []
        assert runner.run_store.load("run-1").status == "waiting_for_approval"

    async def test_a_queued_stage_repeating_itself_is_denied_on_its_own_count(self, runner) -> None:
        """Its count is its own: the surfaced stage changing does not reset it."""
        from app.server.runner import MAX_IDENTICAL_GATES

        record = self._record(runner, auto_approve=True)
        rounds = [
            _paused(f"specialist_ui_ux_{n % 2}", {QUEUED: ("app/b.js", 10.0 + n)})
            for n in range(1, MAX_IDENTICAL_GATES + 2)
        ]
        graph = _RecordingGraph(rounds[1:])

        await runner._handle_state(record, graph, rounds[0], {})

        decided = [update["queued_decisions"][QUEUED]["type"] for update in graph.inputs if update.get("queued_decisions")]
        assert decided[:MAX_IDENTICAL_GATES] == ["approve"] * MAX_IDENTICAL_GATES
        assert decided[MAX_IDENTICAL_GATES] == "reject"

    async def test_the_same_queued_pause_seen_twice_is_counted_once(self, runner) -> None:
        record = self._record(runner, auto_approve=True)
        again = _paused("specialist_ui_ux_1", {QUEUED: ("app/b.js", 5.0)})
        graph = _RecordingGraph([again])

        await runner._handle_state(record, graph, _paused(SURFACED, {QUEUED: ("app/b.js", 5.0)}), {})

        assert graph.inputs[1]["queued_decisions"][QUEUED] == graph.inputs[0]["queued_decisions"][QUEUED]
