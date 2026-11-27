"""A suite written in parts: the part paused at its gate goes on in its own conversation, and the next starts its own.

Measured on one run (18 criteria in three files, every gated tool call pausing the node): part 1 wrote its file and its
next tool call paused. On the decision the loop found part 1's criteria covered and went on to part 2, whose stage
call resumed the pending conversation - part 1's - ran the suite and gave part 1's answer; part 3 and the fill resumed
the same finished conversation. No part 2 or 3 was ever written and the suite went to review with twelve criteria
untested.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.acceptance import suite
from app.graph import abandoned_threads
from app.graph import acceptance_batches as batches
from app.graph import acceptance_nodes as nodes
from app.graph import workflow

BRIEF = "# Brief\n## Features\n- Add a note\n## Acceptance Criteria\n" + "".join(
    f"- Criterion number {n} holds\n" for n in range(1, 12))
CONFIG = {"configurable": {"thread_id": "t"}}
CTX = nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=None)
PAUSE = "awaiting_approval:"


def _state(root: Path) -> dict[str, Any]:
    (root / ".project-directory").write_text("notes\n")
    (root / "notes").mkdir(exist_ok=True)
    suite.save_criteria(root, nodes.number(BRIEF))
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "document": SimpleNamespace(text=BRIEF),
        "product_intake": SimpleNamespace(product_name="Notes", success_measures=[]),
        "stack_selection": SimpleNamespace(technology_stack=SimpleNamespace(product_kind="browser_app")),
    }


def _tests_for(root: Path, part: str, ids) -> None:
    target = root / "notes" / "acceptance" / f"{part}.spec.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(f"test('[{i}] proves it', async () => {{}});\n" for i in ids))


def _ids_asked(request: dict) -> list[str]:
    import re

    text = request["messages"][-1]["content"]
    section = text.split("--- Acceptance criteria ---")[1].split("--- This suite is written")[0].split("--- How to write")[0]
    return re.findall(r"AC-\d+", section)


class _Author:
    """The stage call with the model cut off, as the stage call behaves: handed a decision, it carries on the paused
    conversation (whosever it is) to its answer; otherwise it opens its own, writes its part's tests and, when
    `pauses`, stops at the gate of its next tool call."""

    def __init__(self, root: Path, pauses: bool):
        self.root, self.pauses = root, pauses
        self.calls: list[tuple[str, str]] = []  # (the stage named, the conversation's stage, or "fresh")

    def __call__(self, state, config, *, stage_name, agent, initial_request, output_key, next_stage):
        thread = state.get("pending_inner_thread_id")
        if state.get("pending_decision") is not None and thread:
            self.calls.append((stage_name, thread.split(":")[1]))
            return {output_key: SimpleNamespace(blockers=[]), "stage": next_stage,
                    "pending_decision": None, "pending_inner_thread_id": None, "pending_approval": None}
        self.calls.append((stage_name, "fresh"))
        _tests_for(self.root, stage_name, _ids_asked(initial_request))
        if self.pauses:
            return {"stage": f"{PAUSE}{stage_name}", "pending_inner_thread_id": f"t:{stage_name}:0000abcd",
                    "pending_approval": {"tool": "run_terminal_command"}, "pending_decision": None}
        return {output_key: SimpleNamespace(blockers=[]), "stage": next_stage}


def _author(root, monkeypatch, *, pauses: bool, agent: Any = None) -> _Author:
    fake = _Author(root, pauses)
    monkeypatch.setattr("app.graph.workflow._run_gated_agent", fake)
    monkeypatch.setattr("app.agents.specialists.create_specialist_agent", lambda *a, **k: agent or object())
    monkeypatch.setenv("BATCH_ACCEPTANCE_AUTHOR", "on")
    monkeypatch.setattr(batches, "batch_size", lambda model="": 4)
    monkeypatch.setenv("DELIVERY_MODE", "fast")
    return fake


def test_each_part_paused_at_its_gate_is_answered_in_its_own_conversation_and_the_next_opens_its_own(tmp_path, monkeypatch):
    author = _author(tmp_path, monkeypatch, pauses=True)
    state = _state(tmp_path)

    for _ in range(10):  # the runner: each pause answered, the node entered again
        update = nodes.acceptance_author(state, CONFIG, CTX)
        state = {**state, **update}
        if not str(update.get("stage") or "").startswith(PAUSE):
            break
        state["pending_decision"] = {"type": "approve"}

    assert author.calls == [
        ("acceptance_author_0_g0", "fresh"), ("acceptance_author_0_g0", "acceptance_author_0_g0"),
        ("acceptance_author_0_g1", "fresh"), ("acceptance_author_0_g1", "acceptance_author_0_g1"),
        ("acceptance_author_0_g2", "fresh"), ("acceptance_author_0_g2", "acceptance_author_0_g2"),
    ]
    assert set(suite.coverage(tmp_path)) == {criterion.id for criterion in suite.criteria(tmp_path)}
    assert update["acceptance_round"] == 1


def test_a_part_paused_later_goes_on_first_and_the_parts_before_it_are_not_asked_again(tmp_path, monkeypatch):
    """Part 1 answered with AC-4 untested; part 2 wrote its tests and paused at its gate (part 3's tests are there too)."""
    author = _author(tmp_path, monkeypatch, pauses=False)
    state = _state(tmp_path)
    _tests_for(tmp_path, "acceptance_author_0_g0", ["AC-1", "AC-2", "AC-3"])
    _tests_for(tmp_path, "acceptance_author_0_g1", ["AC-5", "AC-6", "AC-7", "AC-8"])
    _tests_for(tmp_path, "acceptance_author_0_g2", ["AC-9", "AC-10", "AC-11", "AC-12"])
    state.update({"stage": f"{PAUSE}acceptance_author_0_g1", "pending_decision": {"type": "approve"},
                  "pending_inner_thread_id": "t:acceptance_author_0_g1:0000abcd"})

    nodes.acceptance_author(state, CONFIG, CTX)

    assert author.calls == [
        ("acceptance_author_0_g1", "acceptance_author_0_g1"),
        ("acceptance_author_0_fill", "fresh"),  # AC-4, asked for once more alone
    ]


class _SavedConversation:
    """The agent's saved conversations: one with steps still to take, under `thread`."""

    def __init__(self, thread: str):
        self.thread = thread

    def get_state(self, config):
        if config["configurable"]["thread_id"] != self.thread:
            return SimpleNamespace(values={}, next=())
        return SimpleNamespace(values={"messages": [1, 2, 3]}, next=("tools",))


def test_a_part_a_stopped_worker_cut_off_after_its_write_goes_on_before_the_next(tmp_path, monkeypatch):
    """A deploy between part 1's write and its answer: part 1 carries on, then part 2 is asked."""
    thread = "t:acceptance_author_0_g0:0000abcd"
    author = _author(tmp_path, monkeypatch, pauses=False, agent=_SavedConversation(thread))
    state = _state(tmp_path)
    _tests_for(tmp_path, "acceptance_author_0_g0", ["AC-1", "AC-2", "AC-3", "AC-4"])
    abandoned_threads.remember(tmp_path, "t", "acceptance_author_0_g0", thread, process="a-process-that-stopped")

    nodes.acceptance_author(state, CONFIG, CTX)

    assert [name for name, _ in author.calls] == [
        "acceptance_author_0_g0", "acceptance_author_0_g1", "acceptance_author_0_g2"]


class _Agent:
    def __init__(self):
        self.calls: list[tuple[Any, str]] = []

    def get_state(self, config):
        return SimpleNamespace(values={}, next=())

    def invoke(self, request, config=None):
        self.calls.append((request, config["configurable"]["thread_id"]))
        return {"messages": [], "structured_response": "answer"}


def test_a_stage_handed_another_stage_s_decision_starts_its_own_conversation_with_its_request(tmp_path, monkeypatch):
    resumed: list[str] = []
    monkeypatch.setattr(workflow, "resume_with_decision",
                        lambda agent, thread, decision, **kwargs: resumed.append(thread) or {"structured_response": "x"})
    agent = _Agent()

    update = workflow._run_gated_agent(
        {"stage": f"{PAUSE}acceptance_author_0_g0", "repository": SimpleNamespace(root_path=str(tmp_path)),
         "pending_decision": {"type": "approve"}, "pending_inner_thread_id": "outer:acceptance_author_0_g0:0000abcd"},
        {"configurable": {"thread_id": "outer"}},
        stage_name="acceptance_author_0_g1", agent=agent,
        initial_request={"messages": [{"role": "user", "content": "write part 2"}]},
        output_key="out", next_stage="acceptance_review",
    )

    assert resumed == []
    request, thread = agent.calls[0]
    assert request == {"messages": [{"role": "user", "content": "write part 2"}]}
    assert thread.startswith("outer:acceptance_author_0_g1:") and update["out"] == "answer"


def test_a_stage_handed_its_own_decision_still_carries_its_conversation_on(tmp_path, monkeypatch):
    resumed: list[str] = []
    monkeypatch.setattr(workflow, "resume_with_decision",
                        lambda agent, thread, decision, **kwargs: resumed.append(thread) or {"structured_response": "x"})

    update = workflow._run_gated_agent(
        {"stage": f"{PAUSE}acceptance_author_0_g1", "repository": SimpleNamespace(root_path=str(tmp_path)),
         "pending_decision": {"type": "approve"}, "pending_inner_thread_id": "outer:acceptance_author_0_g1:0000abcd"},
        {"configurable": {"thread_id": "outer"}},
        stage_name="acceptance_author_0_g1", agent=_Agent(),
        initial_request={"messages": [{"role": "user", "content": "write part 2"}]},
        output_key="out", next_stage="acceptance_review",
    )

    assert resumed == ["outer:acceptance_author_0_g1:0000abcd"] and update["out"] == "x"
