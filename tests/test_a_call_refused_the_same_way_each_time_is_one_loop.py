"""Calls refused the same way each time are one loop, however much the call itself changes.

The tally of a stage's refused calls counted identical `(name, arguments)`.
Measured on one run: a fixer sent ten shell lines in a minute - each a
different line, each refused as a whole command line in one string - and the
tool was never withheld, because no line was sent twice.
"""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage, ToolMessage

from app.agents.settled_answer import IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL, _a_tool_refused_identically


def _conversation(lines):
    messages = []
    for n, line in enumerate(lines):
        messages.append(AIMessage(content="", tool_calls=[{"id": f"c{n}", "name": "run_terminal_command",
                                                            "args": {"command": [line]}}]))
        messages.append(ToolMessage(tool_call_id=f"c{n}", content=json.dumps({"error": (
            f"'{line}' is a whole command line in one string. There is no shell here, so nothing splits it.")})))
    return messages


def test_different_lines_refused_the_same_way_add_up():
    lines = [f"cd /app && cat file_{n}.py | head -{n}" for n in range(IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL)]
    assert _a_tool_refused_identically(_conversation(lines)) == ("run_terminal_command",
                                                                 IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL)


def test_fewer_than_the_threshold_are_not_yet_a_loop():
    assert _a_tool_refused_identically(_conversation(["cd a && ls", "cd b && ls"])) is None


def test_refusals_of_different_kinds_do_not_add_up():
    messages = _conversation(["cd a && ls"])
    for n, error in enumerate(["'sed' is not permitted for role 'x'.", "Refusing to write 'a.py': it does not parse.",
                               "Not running `cat`: reading is done for this stage."]):
        messages.append(AIMessage(content="", tool_calls=[{"id": f"d{n}", "name": "run_terminal_command",
                                                            "args": {"command": [str(n)]}}]))
        messages.append(ToolMessage(tool_call_id=f"d{n}", content=json.dumps({"error": error})))
    assert _a_tool_refused_identically(messages) is None
