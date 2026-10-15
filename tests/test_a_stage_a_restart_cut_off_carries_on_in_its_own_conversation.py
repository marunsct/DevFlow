"""A stage a stopped worker cut off carries on in its own conversation; a new visit starts fresh.

A deploy waited for a 10-minute frontier call to return - 47,669 tokens of a
revised specification - restarted the worker, and the architect began again
from nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.graph import abandoned_threads
from app.graph.workflow import _run_gated_agent


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
    abandoned_threads.remember(tmp_path, "outer", "principal_architect", "outer:principal_architect:cut")
    agent = _Agent(saved="outer:principal_architect:cut")

    update = _visit(tmp_path, agent)

    assert agent.calls == [(None, "outer:principal_architect:cut")]
    assert update["out"] == "answer"
    assert abandoned_threads._read(tmp_path) == {}


def test_a_note_for_a_conversation_that_had_finished_starts_the_visit_fresh(tmp_path):
    """A note left behind for a finished conversation would hand a later visit the old answer."""
    abandoned_threads.remember(tmp_path, "outer", "principal_architect", "outer:principal_architect:cut")
    agent = _Agent(saved="outer:principal_architect:cut", pending=())

    update = _visit(tmp_path, agent)

    assert agent.calls[0][0] is not None and agent.calls[0][1] != "outer:principal_architect:cut"
    assert update["out"] == "answer"


def test_a_note_with_no_saved_steps_starts_fresh(tmp_path):
    abandoned_threads.remember(tmp_path, "outer", "principal_architect", "outer:principal_architect:empty")
    agent = _Agent(saved=None)

    _visit(tmp_path, agent)

    assert agent.calls[0][0] is not None and agent.calls[0][1] != "outer:principal_architect:empty"
