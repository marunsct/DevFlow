"""Each call names, at its end, the files and command results the conversation already holds (Initiative R).

17-47% of tool calls across runs were exact repeats, most of them reads of a
file the conversation already had. The pointer and withholding rungs answer a
repeat after it is made; this names what is already there so it need not be.
"""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.workspace_digest import already_known


def _conversation():
    return [
        HumanMessage(content="fix it"),
        AIMessage(content="", tool_calls=[{"id": "a", "name": "read_file", "args": {"file_path": "app/main.py"}},
                                          {"id": "b", "name": "read_file", "args": {"file_path": "app/db.py"}}]),
        ToolMessage(content="1 import x", tool_call_id="a"),
        ToolMessage(content="1 import y", tool_call_id="b"),
        AIMessage(content="", tool_calls=[{"id": "c", "name": "edit_artifact", "args": {"relative_path": "app/main.py"}}]),
        ToolMessage(content='{"status": "edited"}', tool_call_id="c"),
        AIMessage(content="", tool_calls=[{"id": "d", "name": "run_terminal_command",
                                           "args": {"command": ["npm", "test"]}}]),
        ToolMessage(content='{"returncode": 1, "stdout": "1 failing"}', tool_call_id="d"),
        AIMessage(content="", tool_calls=[{"id": "e", "name": "read_file", "args": {"file_path": "gone.py"}}]),
        ToolMessage(content="Error: no such file", tool_call_id="e"),
    ]


def test_the_files_read_and_the_commands_run_are_named() -> None:
    known = already_known(_conversation())

    assert "app/db.py (call 2)" in known
    assert "app/main.py (call 1; changed by your write at call 3)" in known
    assert "`npm test` -> exit 1 (call 4)" in known
    assert "gone.py" not in known


def test_a_conversation_that_read_nothing_gets_nothing() -> None:
    assert already_known([HumanMessage(content="plan it")]) == ""


def test_the_same_conversation_gives_the_same_bytes() -> None:
    assert already_known(_conversation()) == already_known(_conversation())


def test_the_digest_carries_it_and_it_can_be_switched_off(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    from app.agents.workspace_digest import build_workspace_digest_middleware

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("x = 1\n")

    class Request(SimpleNamespace):
        def override(self, **changes):
            return Request(**{**self.__dict__, **changes})

    seen = []
    middleware = build_workspace_digest_middleware(str(tmp_path))
    middleware.wrap_model_call(Request(messages=_conversation()), lambda r: seen.append(r.messages[-1]["content"]))
    assert "Files already in this conversation" in seen[-1]
    monkeypatch.setenv("ALREADY_KNOWN", "0")
    middleware.wrap_model_call(Request(messages=_conversation()), lambda r: seen.append(r.messages[-1]["content"]))
    assert "Files already in this conversation" not in seen[-1]


def test_its_wording_avoids_the_banned_words() -> None:
    text = re.sub(r"`[^`]*`|\S+\.py", "", already_known(_conversation())).lower()
    assert not set(re.findall(r"[\w-]+", text)) & {"task", "tasks", "to-do", "todo", "button", "click", "checkbox"}


# --- Initiative AO.9: which lines a read covered ------------------------------------

def _numbered(first: int, last: int) -> str:
    return "\n".join(f"{n:>4}  line {n}" for n in range(first, last + 1))


def test_a_read_of_part_of_a_file_says_which_part() -> None:
    messages = [
        HumanMessage(content="fix it"),
        AIMessage(content="", tool_calls=[{"id": "a", "name": "read_file", "args": {"file_path": "app/big.py", "limit": 200}}]),
        ToolMessage(content=_numbered(1, 200), tool_call_id="a"),
        AIMessage(content="", tool_calls=[{"id": "b", "name": "read_file", "args": {"file_path": "app/big.py", "offset": 300}}]),
        ToolMessage(content=_numbered(301, 340), tool_call_id="b"),
        AIMessage(content="", tool_calls=[{"id": "c", "name": "read_file", "args": {"file_path": "app/small.py"}}]),
        ToolMessage(content=_numbered(1, 12), tool_call_id="c"),
    ]

    known = already_known(messages)

    assert "app/big.py (call 2; lines 1–200, 301–340)" in known
    assert "app/small.py (call 3; lines 1–12)" in known


def test_touching_ranges_are_one_range_and_a_write_forgets_what_was_read() -> None:
    messages = [
        HumanMessage(content="fix it"),
        AIMessage(content="", tool_calls=[{"id": "a", "name": "read_file", "args": {"file_path": "app/x.py"}}]),
        ToolMessage(content=_numbered(1, 50), tool_call_id="a"),
        AIMessage(content="", tool_calls=[{"id": "b", "name": "read_file", "args": {"file_path": "app/x.py", "offset": 50}}]),
        ToolMessage(content=_numbered(51, 90), tool_call_id="b"),
        AIMessage(content="", tool_calls=[{"id": "c", "name": "edit_artifact", "args": {"relative_path": "app/x.py"}}]),
        ToolMessage(content='{"status": "edited"}', tool_call_id="c"),
    ]

    known = already_known(messages)

    assert "lines 1–50" not in known
    assert "app/x.py (call 2; changed by your write at call 3)" in known
    assert "lines 1–90" in already_known(messages[:5])
