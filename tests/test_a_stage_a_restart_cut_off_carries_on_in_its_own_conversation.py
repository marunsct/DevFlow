"""A stage a stopped worker cut off carries on in its own conversation; a new visit starts fresh.

A deploy waited for a 10-minute frontier call to return - 47,669 tokens of a
revised specification - restarted the worker, and the architect began again
from nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.graph import abandoned_threads
from app.graph.workflow import _run_gated_agent


def _cut_off_by_another_process(root, stage, thread):
    """A note as a process that has since stopped left it."""
    abandoned_threads.remember(root, "outer", stage, thread)
    data = abandoned_threads._read(root)
    data[f"outer|{stage}"]["process"] = "a-process-that-stopped"
    abandoned_threads._write(root, data)


class _Agent:
    def __init__(self, saved=None, pending=("tools",)):
        self.saved, self.pending, self.calls = saved, pending, []

    def get_state(self, config):
        if self.saved is None or config["configurable"]["thread_id"] != self.saved:
            return SimpleNamespace(values={}, next=())
        return SimpleNamespace(values={"messages": [1, 2, 3], "structured_response": "done"}, next=self.pending)

    def invoke(self, request, config=None):
        self.calls.append((request, config["configurable"]["thread_id"]))
        return {"messages": [], "structured_response": "answer"}


def _visit(root, agent):
    return _run_gated_agent(
        {"stage": "principal_architect", "repository": SimpleNamespace(root_path=str(root))},
        {"configurable": {"thread_id": "outer"}},
        stage_name="principal_architect", agent=agent, initial_request={"messages": [{"role": "user", "content": "write"}]},
        output_key="out", next_stage="architecture_review",
    )


def test_a_visit_starts_fresh_and_crosses_its_conversation_out_when_it_returns(tmp_path):
    agent = _Agent()
    _visit(tmp_path, agent)

    request, thread = agent.calls[0]
    assert request is not None and thread.startswith("outer:principal_architect:")
    assert abandoned_threads._read(tmp_path) == {}


def test_a_visit_a_stopped_worker_cut_off_carries_on_from_its_last_step(tmp_path):
    _cut_off_by_another_process(tmp_path, "principal_architect", "outer:principal_architect:cut")
    agent = _Agent(saved="outer:principal_architect:cut")

    update = _visit(tmp_path, agent)

    assert agent.calls == [(None, "outer:principal_architect:cut")]
    assert update["out"] == "answer"
    assert abandoned_threads._read(tmp_path) == {}


def test_a_note_for_a_conversation_that_had_finished_starts_the_visit_fresh(tmp_path):
    """A note left behind for a finished conversation would hand a later visit the old answer."""
    _cut_off_by_another_process(tmp_path, "principal_architect", "outer:principal_architect:cut")
    agent = _Agent(saved="outer:principal_architect:cut", pending=())

    update = _visit(tmp_path, agent)

    assert agent.calls[0][0] is not None and agent.calls[0][1] != "outer:principal_architect:cut"
    assert update["out"] == "answer"


def test_a_note_with_no_saved_steps_starts_fresh(tmp_path):
    _cut_off_by_another_process(tmp_path, "principal_architect", "outer:principal_architect:empty")
    agent = _Agent(saved=None)

    _visit(tmp_path, agent)

    assert agent.calls[0][0] is not None and agent.calls[0][1] != "outer:principal_architect:empty"


def test_a_note_this_process_left_is_a_new_attempt_not_a_cut_off(tmp_path):
    """A plan sent back in the same process found its note and carried on the old conversation."""
    abandoned_threads.remember(tmp_path, "outer", "technical_lead", "outer:technical_lead:old")
    agent = _Agent(saved="outer:technical_lead:old")

    _run_gated_agent(
        {"stage": "technical_lead", "repository": SimpleNamespace(root_path=str(tmp_path))},
        {"configurable": {"thread_id": "outer"}},
        stage_name="technical_lead", agent=agent, initial_request={"messages": [{"role": "user", "content": "plan"}]},
        output_key="out", next_stage="next",
    )

    assert agent.calls[0][0] is not None and agent.calls[0][1] != "outer:technical_lead:old"


def test_a_decision_with_no_gate_waiting_for_it_starts_the_stage_with_its_request(tmp_path):
    """Measured on one run: rewound while its record still named another stage's gate,
    the resume answered that gate, and the rewound review ran on a made-up conversation
    holding only the project memory - never the request built for it."""
    agent = _Agent()

    update = _run_gated_agent(
        {"stage": "architecture_review", "repository": SimpleNamespace(root_path=str(tmp_path)),
         "pending_decision": {"type": "approve"}, "pending_inner_thread_id": None},
        {"configurable": {"thread_id": "outer"}},
        stage_name="architecture_review", agent=agent,
        initial_request={"messages": [{"role": "user", "content": "review this"}]},
        output_key="out", next_stage="scrum_master",
    )

    request, thread = agent.calls[0]
    assert request == {"messages": [{"role": "user", "content": "review this"}]}
    assert thread.startswith("outer:architecture_review:") and update["out"] == "answer"


def test_after_a_transient_model_error_the_retry_carries_the_conversation_on(tmp_path):
    """Measured on one run: the model server refused one malformed reply, the stage was
    retried in a new conversation, and 25 calls of work were thrown away."""

    class _Flaky(_Agent):
        def __init__(self):
            super().__init__()
            self.failed = False

        def get_state(self, config):
            if self.calls and config["configurable"]["thread_id"] == self.calls[0][1]:
                return SimpleNamespace(values={"messages": [1, 2, 3]}, next=("model",))
            return SimpleNamespace(values={}, next=())

        def invoke(self, request, config=None):
            self.calls.append((request, config["configurable"]["thread_id"]))
            if not self.failed:
                self.failed = True
                raise RuntimeError("Error code: 500 - {'type': 'server_error'} The model produced output that does not match "
                                   "the expected peg-native format")
            return {"messages": [], "structured_response": "answer"}

    agent = _Flaky()
    state = {"stage": "principal_architect", "repository": SimpleNamespace(root_path=str(tmp_path))}

    first = _run_gated_agent(
        state, {"configurable": {"thread_id": "outer"}},
        stage_name="principal_architect", agent=agent, initial_request={"messages": [{"role": "user", "content": "write"}]},
        output_key="out", next_stage="architecture_review",
    )
    assert "out" not in first  # handed back for a retry
    update = _visit(tmp_path, agent)

    (_, thread), (again, same) = agent.calls
    assert again is None and same == thread and update["out"] == "answer"
    assert abandoned_threads._read(tmp_path) == {}


def test_a_transient_error_after_an_approved_tool_call_also_carries_the_conversation_on(tmp_path, monkeypatch):
    # Measured on one run: with every gated tool call resumed through a decision,
    # most model calls run on that path, and its retry started the stage over.
    from app.graph import workflow

    def resume(agent, thread, decision, **kwargs):
        raise RuntimeError("Error code: 500 - {'type': 'server_error'} malformed output")

    monkeypatch.setattr(workflow, "resume_with_decision", resume)
    agent = _Agent(saved="outer:principal_architect:paused", pending=("model",))
    state = {"stage": "principal_architect", "repository": SimpleNamespace(root_path=str(tmp_path)),
             "pending_decision": {"type": "approve"}, "pending_inner_thread_id": "outer:principal_architect:paused"}

    first = _run_gated_agent(
        state, {"configurable": {"thread_id": "outer"}},
        stage_name="principal_architect", agent=agent, initial_request={"messages": [{"role": "user", "content": "write"}]},
        output_key="out", next_stage="architecture_review",
    )
    assert "out" not in first
    _visit(tmp_path, agent)

    assert agent.calls == [(None, "outer:principal_architect:paused")]
