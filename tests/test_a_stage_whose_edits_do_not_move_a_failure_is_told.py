"""A stage whose edits do not change a failing test run is told so, and then left its answer.

The stuck shape a repeat check misses: edit, run the tests, the same failure,
edit again - every call new, nothing moving.
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents.settled_answer import (
    SAME_FAILURE_BEFORE_SAYING_SO,
    SAME_FAILURE_BEFORE_THE_ANSWER,
    build_settled_answer_middleware,
)

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class Fix(BaseModel):
    summary: str


class _Request:
    def __init__(self, messages):
        self.messages, self.tools, self.captured = messages, ["edit_artifact", "run_terminal_command"], {}

    def override(self, **changes):
        self.captured.update(changes)
        return self


def _stage(runs: int, *, same: bool = True, edits: bool = True) -> list:
    messages: list = [HumanMessage(content="fix the defect")]
    for n in range(runs):
        if edits:
            messages.append(AIMessage(content="", id=f"e{n}", tool_calls=[{"name": "edit_artifact", "args": {"relative_path": "src/app.ts", "find": f"a{n}", "replace": f"b{n}"}, "id": f"ed{n}"}]))
            messages.append(ToolMessage(content='{"status": "edited"}', tool_call_id=f"ed{n}"))
        messages.append(AIMessage(content="", id=f"t{n}", tool_calls=[{"name": "run_terminal_command", "args": {"command": ["node", "--test", "tests/app.test.ts"]}, "id": f"run{n}"}]))
        failing = "not ok 3 - DELETE answers 204" if same else f"not ok {n} - case {n}"
        messages.append(ToolMessage(content=json.dumps({"stdout": f"{failing} ({12 + n}.5ms)\n# fail 1", "stderr": "", "returncode": "1"}), tool_call_id=f"run{n}"))
    return messages


def _captured(messages):
    request = _Request(messages)
    build_settled_answer_middleware(Fix, "defect_fix_1_0", 120).wrap_model_call(request, lambda r: r)
    return request.captured


def test_the_same_failure_after_each_edit_is_named_then_leaves_the_answer():
    told = _captured(_stage(SAME_FAILURE_BEFORE_SAYING_SO))
    notice = str(told["messages"][-1])
    assert "failed in exactly the same way" in notice and "node --test tests/app.test.ts" in notice
    assert told.get("tools") != []
    assert not BANNED.search(notice)

    assert _captured(_stage(SAME_FAILURE_BEFORE_THE_ANSWER)).get("tools") == []


def test_a_failure_that_changes_or_runs_with_no_edits_between_is_left_alone():
    assert "failed in exactly the same way" not in str(_captured(_stage(SAME_FAILURE_BEFORE_THE_ANSWER, same=False)).get("messages"))
    assert "failed in exactly the same way" not in str(_captured(_stage(SAME_FAILURE_BEFORE_THE_ANSWER, edits=False)).get("messages"))
