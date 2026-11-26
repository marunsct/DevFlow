"""A builder or fixer that reaches its step limit settles with what it wrote; it does not fail the run (LF.1578).

Measured on a medium run in parallel mode: a backend builder, sent back unfinished by the check of each work order
against what it promised, read to its step limit on three fresh conversations ("ran 160 steps without finishing") and
the run failed, with the files it had written on disk. The same stage returning without an answer is recorded as
blocked and the build goes on; at its call budget, a writing stage is recorded from the files it wrote. The step-limit
path did neither, in the linear builder and the parallel worker alike (both run `_run_gated_agent`).
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.graph.workflow import _max_structured_retries, _run_gated_agent

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ROUTES = "task-management-dashboard/task_management_dashboard/routes.py"
#: The captured visit's last calls: reads only, in a fresh conversation after the stage was sent back.
ONLY_READ = [
    HumanMessage(content="Build the routes"),
    AIMessage(content="", tool_calls=[{"name": "read_file", "id": "r1", "args": {"file_path": f"/{ROUTES}"}}]),
    ToolMessage(content="     1\tfrom fastapi import APIRouter\n", tool_call_id="r1", name="read_file"),
]
EDITED = [
    *ONLY_READ,
    AIMessage(content="", tool_calls=[{"name": "edit_artifact", "id": "e1",
                                       "args": {"relative_path": ROUTES, "find": "a", "replace": "b"}}]),
    ToolMessage(content="{'status': 'edited'}", tool_call_id="e1", name="edit_artifact"),
]


class _Spins:
    """A role agent that reaches its step limit; its checkpoint holds `messages`."""

    workflow_response_format = None

    def __init__(self, messages: list) -> None:
        self.messages = messages

    def invoke(self, request, config=None):  # noqa: ARG002
        from langgraph.errors import GraphRecursionError

        raise GraphRecursionError("Recursion limit of 160 reached without hitting a stop condition")

    def get_state(self, config):  # noqa: ARG002
        return SimpleNamespace(values={"messages": self.messages}, next=())


def _spins(*args, **kwargs):
    from langgraph.errors import GraphRecursionError

    raise GraphRecursionError("Recursion limit of 160 reached without hitting a stop condition")


def _run(tmp_path, monkeypatch, stage: str, messages: list, *, restarts_spent: bool, resumed: bool = False) -> dict:
    monkeypatch.setattr("app.graph.workflow.resume_with_decision", _spins)
    state = {"stage": stage, "repository": SimpleNamespace(root_path=str(tmp_path))}
    if restarts_spent:
        state["structured_retries"] = {stage: _max_structured_retries()}
    if resumed:
        state.update(pending_decision={"type": "approve"}, pending_inner_thread_id=f"outer:{stage}:1")
    return _run_gated_agent(
        state, {"configurable": {"thread_id": "outer"}}, stage_name=stage, agent=_Spins(messages),
        initial_request={"messages": [{"role": "user", "content": "build"}]},
        output_key="out", next_stage="specialist_dispatch",
    )


@pytest.mark.parametrize("resumed", [False, True], ids=["fresh", "after-an-approval"])
def test_a_builder_out_of_restarts_is_recorded_unfinished_and_the_build_goes_on(tmp_path, monkeypatch, resumed):
    update = _run(tmp_path, monkeypatch, "specialist_backend_0", ONLY_READ, restarts_spent=True, resumed=resumed)

    assert update["stage"] == "specialist_dispatch"
    assert "step limit" in update["out"].blockers[0] and "unfinished" in update["out"].blockers[0]


def test_a_builder_that_wrote_is_recorded_from_its_writes_without_a_restart(tmp_path, monkeypatch):
    update = _run(tmp_path, monkeypatch, "specialist_backend_0", EDITED, restarts_spent=False)

    assert update["stage"] == "specialist_dispatch"
    assert update["out"].changed_files == [ROUTES]
    assert "structured_retries" not in update


def test_a_fixer_out_of_restarts_leaves_its_defect_to_the_next_round(tmp_path, monkeypatch):
    update = _run(tmp_path, monkeypatch, "defect_fix_1_0", ONLY_READ, restarts_spent=True)

    assert update["stage"] == "specialist_dispatch" and update["out"].blockers


def test_a_stage_with_no_deliverable_still_fails_the_run(tmp_path, monkeypatch):
    update = _run(tmp_path, monkeypatch, "principal_architect", ONLY_READ, restarts_spent=True)

    assert update["stage"] == "failed"
    assert "steps without finishing" in update["error"]


def test_the_blocker_avoids_the_banned_words(tmp_path, monkeypatch):
    update = _run(tmp_path, monkeypatch, "specialist_backend_0", [], restarts_spent=True)

    assert not BANNED.search(update["out"].blockers[0])
