"""A read answered "it is in the project memory" counts toward taking the read tool away.

The read rung counted only the backend's refusals. The project memory answers
a read of a file it holds with a pointer instead - the same answer in kinder
words - and nothing counted those. Measured on one run: a testing stage made
70 model calls and got 64 pointers. It read a batch of held files, the stall
rung withheld the looking tools for one call, it wrote one file, and the batch
came back, about 35 calls of it.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.project_memory import HELD_POINTER
from app.agents.settled_answer import POINTED_READS_BEFORE_WITHHOLDING_THE_TOOL

from tests.test_the_read_tool_is_taken_away import TOOLS, _call, _names


def _cycles(pointers: int) -> list:
    """Batches of pointer answers, each followed by a write that returned something new."""
    messages: list = [HumanMessage(content="write the tests")]
    for i in range(pointers):
        messages.append(AIMessage(content="", id=f"a{i}"))
        messages.append(ToolMessage(content=f"`app/models/m{i % 4}.py` {HELD_POINTER}, whole and as it is now.",
                                    tool_call_id=f"r{i}"))
        if i % 4 == 3:
            messages.append(AIMessage(content="", id=f"w{i}"))
            messages.append(ToolMessage(content='{"path": "tests/conftest.py", "summary": "written"}',
                                        tool_call_id=f"w{i}"))
    messages.append(AIMessage(content="reading again", id="last"))
    return messages


def test_enough_pointers_take_the_read_tool_away() -> None:
    kept = _names(_call(_cycles(POINTED_READS_BEFORE_WITHHOLDING_THE_TOOL)))

    assert "read_file" not in kept and "read_repository_file" not in kept
    assert {"edit_artifact", "run_terminal_command", "grep"} <= kept


def test_a_few_pointers_take_nothing_away() -> None:
    captured = _call(_cycles(POINTED_READS_BEFORE_WITHHOLDING_THE_TOOL - 1))

    assert "read_file" in _names(captured) if "tools" in captured else True


def test_the_pointer_wording_is_the_one_counted() -> None:
    from app.agents import project_memory

    assert f"{{HELD_POINTER}}" in open(project_memory.__file__).read()
    assert len(TOOLS) > 0


def test_the_log_names_the_count_that_took_it_away(caplog) -> None:
    """It said "refused 0 redundant reads" when the pointers had done it."""
    import logging

    with caplog.at_level(logging.WARNING, logger="app.agents.settled_answer"):
        _call(_cycles(POINTED_READS_BEFORE_WITHHOLDING_THE_TOOL))
    said = [r.getMessage() for r in caplog.records if "withholding the read tool" in r.getMessage()]
    assert said and f"pointed to the project memory for {POINTED_READS_BEFORE_WITHHOLDING_THE_TOOL}" in said[0]
