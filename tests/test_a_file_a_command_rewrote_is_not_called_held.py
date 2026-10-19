"""A file a command rewrote is not called held by the conversation (Initiative AO.9).

The already-known list said "Files already in this conversation (scroll up
rather than read again)" about a file a formatter, a generator or an install
had rewritten since it was read: the sandbox kept no receipt of what a command
wrote. A command's result now names the files it changed, and the list says so.
"""
from __future__ import annotations

import json
import os
import time

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.workspace_digest import already_known
from app.tools import sandbox


def test_the_sandbox_names_the_files_changed_since_a_moment(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "node_modules").mkdir()
    old = tmp_path / "app" / "old.py"
    old.write_text("x\n")
    os.utime(old, (time.time() - 60, time.time() - 60))
    moment = time.time() - 1
    (tmp_path / "app" / "main.py").write_text("y\n")
    (tmp_path / "node_modules" / "dep.js").write_text("z\n")

    assert sandbox.files_changed_since(str(tmp_path), moment) == ["app/main.py"]


def test_a_read_file_a_command_changed_is_said_to_have_changed():
    result = json.dumps({"stdout": "formatted", "stderr": "", "returncode": "0", "files_changed": ["app/main.py"]})
    messages = [
        HumanMessage(content="fix it"),
        AIMessage(content="", tool_calls=[{"id": "a", "name": "read_file", "args": {"file_path": "app/main.py"}}]),
        ToolMessage(content="1 import x", tool_call_id="a"),
        AIMessage(content="", tool_calls=[{"id": "b", "name": "run_terminal_command",
                                           "args": {"command": ["npm", "run", "format"]}}]),
        ToolMessage(content=result, tool_call_id="b"),
    ]

    known = already_known(messages)

    assert "app/main.py (call 1; changed by your command at call 2)" in known
    assert "`npm run format` -> exit 0 (call 2)" in known


def test_a_command_whose_output_was_cut_names_where_the_whole_output_is():
    """Measured live: a stage read "call 7" from this list and asked
    `read_command_output` for "call 7", which names no output."""
    result = json.dumps({"stdout": "1 failing\n\n...[8000 bytes omitted; full output saved as 1792-run-x-testing-npm-stdout-ab12.log]\nend",
                         "stderr": "", "returncode": "1"})
    messages = [
        HumanMessage(content="fix it"),
        AIMessage(content="", tool_calls=[{"id": "a", "name": "run_terminal_command", "args": {"command": ["npm", "test"]}}]),
        ToolMessage(content=result, tool_call_id="a"),
    ]

    known = already_known(messages)

    assert "`npm test` -> exit 1; full output: read_command_output('1792-run-x-testing-npm-stdout-ab12.log') (call 1)" in known
