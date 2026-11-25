"""After a stage answers, it is asked to fix only errors in files it may write (PA.8).

Measured on a small run: a testing work order wrote its test file and answered; the check after the answer ran the
compiler, which reported an error in the product's entry file, and the stage was told "fix these errors now". That
file is a builder's, so every write to it was refused (12 refusals, 5 after its first answer) and the stage answered
4 times in one visit. Its budget notice meanwhile said it had NOT written a structured response.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


class _Agent:
    """A role agent that wrote one file and answered; every later turn is recorded and changes nothing."""

    def __init__(self, wrote: str, answer) -> None:
        self.wrote, self.answer, self.asked = wrote, answer, []

    def get_state(self, config):
        return SimpleNamespace(values={}, next=())

    def invoke(self, request, config=None):
        self.asked.append(request)
        if len(self.asked) > 1:
            return {"messages": [AIMessage(content="done")], "structured_response": self.answer}
        return {"messages": [
            AIMessage(content="", tool_calls=[{"name": "write_artifact", "id": "w1",
                                               "args": {"relative_path": self.wrote, "content": "x"}}]),
            ToolMessage(content='{"status": "written"}', tool_call_id="w1"),
        ], "structured_response": self.answer}


def _a_stage_that_answered(tmp_path: Path, monkeypatch, stage: str, wrote: str, compiler_says: list[dict]):
    """`stage` wrote `wrote` and answered; the compiler (the sandbox's edge) reports `compiler_says`."""
    from app.agents.specialists import SpecialistOutput
    from app.graph import workflow

    for path in ("proj/src/main.rs", "proj/tests/notes_test.rs"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("fn main() {}\n")
    monkeypatch.setattr("app.analysis.compiler_check.findings", lambda *args, **kwargs: [dict(f) for f in compiler_says])
    agent = _Agent(wrote, SpecialistOutput(changed_files=[wrote], tests=[wrote]))
    update = workflow._run_gated_agent(
        {"stage": stage, "repository": SimpleNamespace(root_path=str(tmp_path))},
        {"configurable": {"thread_id": "outer"}},
        stage_name=stage, agent=agent,
        initial_request={"messages": [{"role": "user", "content": "write the tests"}]},
        output_key="out", next_stage="specialist_dispatch",
    )
    return update, agent


def test_a_testing_stage_is_not_asked_to_fix_a_product_file_and_its_answer_carries_the_error(tmp_path, monkeypatch):
    update, agent = _a_stage_that_answered(
        tmp_path, monkeypatch, "specialist_testing_1", "proj/tests/notes_test.rs",
        [{"file": "proj/src/main.rs", "line": 7, "message": "error[E0603]: module `store` is private", "code": "error"}],
    )

    assert len(agent.asked) == 1, "no turn asks it to fix a file it may not write"
    blockers = update["out"].blockers
    assert any("proj/src/main.rs" in line and "module `store` is private" in line for line in blockers)


def test_an_error_in_its_own_test_file_is_still_put_to_it(tmp_path, monkeypatch):
    update, agent = _a_stage_that_answered(
        tmp_path, monkeypatch, "specialist_testing_1", "proj/tests/notes_test.rs",
        [{"file": "proj/tests/notes_test.rs", "line": 3, "message": "cannot find function `make`", "code": "error"}],
    )

    assert len(agent.asked) == 2
    assert "proj/tests/notes_test.rs" in agent.asked[1]["messages"][-1]["content"]
    assert not update["out"].blockers


def test_the_error_reaches_the_builder_that_owns_the_file(tmp_path, monkeypatch):
    """A testing work order's kept error is recorded for the builder of the file, as its refused changes are."""
    from app.tools import testing_blockers

    _a_stage_that_answered(
        tmp_path, monkeypatch, "specialist_testing_1", "proj/tests/notes_test.rs",
        [{"file": "proj/src/main.rs", "line": 7, "message": "module `store` is private", "code": "error"}],
    )

    recorded = testing_blockers.recorded(tmp_path, "specialist_testing_1")
    assert list(recorded) == ["proj/src/main.rs"]
    assert "module `store` is private" in recorded["proj/src/main.rs"]["needed"]


def test_a_stage_s_blocker_for_another_s_file_holds_none_of_the_banned_words(tmp_path):
    from app.graph import its_own_to_fix

    lines = its_own_to_fix.blocker_lines(
        str(tmp_path), "test_round_0", ["- In `proj/src/main.rs` line 7: module `store` is private (the compiler)"])

    assert lines
    for line in lines:
        outside = re.sub(r"`[^`]*`", "", line).lower()
        for word in BANNED:
            assert not re.search(rf"\b{re.escape(word)}\b", outside), (word, line)


def test_a_budget_notice_knows_an_answer_sent_through_the_answer_tool():
    """The answer tool is named after the schema; its answer is in the call, not in the message's text."""
    from app.agents.settled_answer import _running_out_of_room
    from app.agents.specialists import SpecialistOutput

    messages = [AIMessage(content="", id="a0", tool_calls=[
        {"name": "SpecialistOutput", "id": "r1", "args": {"changed_files": ["proj/tests/notes_test.rs"]}}])]
    messages += [AIMessage(content=f"step {i}", id=f"m{i}") for i in range(30)]

    notice = _running_out_of_room(messages, 40, SpecialistOutput)

    assert "NOT written" not in notice
    assert "already written an answer" in notice
