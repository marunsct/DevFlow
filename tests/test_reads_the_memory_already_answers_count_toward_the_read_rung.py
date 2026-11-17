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

from app.agents.settled_answer import POINTED_READS_BEFORE_WITHHOLDING_THE_TOOL

from tests.test_the_read_tool_is_taken_away import _call, _names


def _pointers() -> dict[str, str]:
    """What the project memory answers a repeated read of each file it holds with, from the real middleware."""
    import tempfile
    from pathlib import Path
    from types import SimpleNamespace

    from app.agents import project_memory, stage_memory

    root = Path(tempfile.mkdtemp())
    (root / "app" / "models").mkdir(parents=True)
    for i in range(4):
        (root / "app" / "models" / f"m{i}.py").write_text(f"value = {i}\n")
    middleware = project_memory.build_project_memory_middleware(str(root))

    class Request(SimpleNamespace):
        def override(self, **changes):
            return Request(**{**self.__dict__, **changes})

    answers = {}
    with stage_memory.remembering("pointers"):
        middleware.wrap_model_call(Request(messages=[HumanMessage(content="write the tests")], model=None), lambda r: None)
        for i in range(4):
            call = SimpleNamespace(tool_call={"name": "read_file", "args": {"file_path": f"/app/models/m{i}.py"}, "id": "r"})
            for _ in range(2):
                answers[f"m{i}"] = str(middleware.wrap_tool_call(call, lambda r: ToolMessage(content="read", tool_call_id="r")).content)
    stage_memory.forget_everything()
    return answers


POINTERS = _pointers()


def _cycles(pointers: int) -> list:
    """Batches of pointer answers, each followed by a write that returned something new."""
    messages: list = [HumanMessage(content="write the tests")]
    for i in range(pointers):
        messages.append(AIMessage(content="", id=f"a{i}"))
        messages.append(ToolMessage(content=POINTERS[f"m{i % 4}"], tool_call_id=f"r{i}"))
        if i % 4 == 3:
            messages.append(AIMessage(content="", id=f"w{i}"))
            messages.append(ToolMessage(content='{"path": "tests/conftest.py", "summary": "written"}',
                                        tool_call_id=f"w{i}"))
    messages.append(AIMessage(content="reading again", id="last"))
    return messages


def test_enough_pointers_take_the_read_tool_away(monkeypatch) -> None:
    # STABLE_TOOLS off: this checks the bound tool list, which that fix keeps whole (it refuses a withheld call).
    monkeypatch.setenv("STABLE_TOOLS", "off")
    kept = _names(_call(_cycles(POINTED_READS_BEFORE_WITHHOLDING_THE_TOOL)))

    assert "read_file" not in kept and "read_repository_file" not in kept
    assert {"edit_artifact", "run_terminal_command", "grep"} <= kept


def _each_followed_by_a_write(pointers: int) -> list:
    """Pointer answers with a write that returned something new after each one."""
    messages: list = [HumanMessage(content="write the tests")]
    for i in range(pointers):
        messages.append(AIMessage(content="", id=f"a{i}"))
        messages.append(ToolMessage(content=POINTERS[f"m{i % 4}"], tool_call_id=f"r{i}"))
        messages.append(AIMessage(content="", id=f"w{i}"))
        messages.append(ToolMessage(content='{"path": "tests/conftest.py", "summary": "written"}',
                                    tool_call_id=f"w{i}"))
    messages.append(AIMessage(content="reading again", id="last"))
    return messages


def test_a_few_pointers_take_nothing_away() -> None:
    # Two in a row are a stall since Initiative BC; apart, with work between
    # them, they are counted toward the read rung and take nothing yet.
    captured = _call(_each_followed_by_a_write(POINTED_READS_BEFORE_WITHHOLDING_THE_TOOL - 1))

    assert "read_file" in _names(captured) if "tools" in captured else True
