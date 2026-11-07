"""The setup stage's declaration is written even when the stall guard has withheld its writes (SF bug).

Measured on the first custom-stack baseline, after a rewind: the setup stage spent its calls reading what an earlier
attempt left, wrote `stack-setup.json` last - the one file the harness proves the setup from - and the write was
refused because `write_artifact` was withheld at that point of the stage. The next attempt never wrote it, and the
setup was left to the agents. Withholding stops a stalling stage; it must not refuse the stage's own deliverable.
"""
from __future__ import annotations

from types import SimpleNamespace

from pydantic import BaseModel

from app.agents.settled_answer import build_settled_answer_middleware


class Answer(BaseModel):
    done: bool = True


def _middleware():
    middleware = build_settled_answer_middleware(Answer, "stack_setup_0", 40)
    middleware._withheld = {"write_artifact", "edit_artifact"}
    return middleware


def _request(name, path):
    return SimpleNamespace(tool_call={"id": "c1", "name": name, "args": {"relative_path": path, "content": "{}"}})


def test_the_declaration_is_written_though_writes_are_withheld():
    ran = []
    _middleware().wrap_tool_call(_request("write_artifact", "notes-api/stack-setup.json"), lambda r: ran.append(r) or "ok")
    assert ran


def test_any_other_write_is_still_refused():
    ran = []
    answer = _middleware().wrap_tool_call(_request("write_artifact", "notes-api/app.py"), lambda r: ran.append(r) or "ok")
    assert not ran and "withheld" in str(answer.content)


def test_the_exempt_name_is_the_setup_s_declaration():
    from app.agents.settled_answer import DELIVERABLE_FILES
    from app.stacks.custom_setup import DECLARATION_FILE

    assert DECLARATION_FILE in DELIVERABLE_FILES
