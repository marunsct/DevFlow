"""A call to a withheld tool is refused with the tools still left named, or told to answer when none is.

Per-role audit over 30 runs: 57 refusals of withheld tools in 18 runs; each said only "the tools you were offered", and
stages called another withheld tool next.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from pydantic import BaseModel

from app.agents.settled_answer import build_settled_answer_middleware

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class Answer(BaseModel):
    summary: str


def _refusal(middleware, name):
    request = SimpleNamespace(tool_call={"name": name, "id": "c1", "args": {"file_path": "a.py"}})
    return str(middleware.wrap_tool_call(request, lambda r: "ran").content)


def test_the_refusal_names_the_tools_still_left():
    middleware = build_settled_answer_middleware(Answer, "defect_fix_1_0", 60)
    middleware._set_withheld({"read_file", "ls"}, {"read_file", "ls", "edit_artifact", "run_terminal_command"})
    said = _refusal(middleware, "read_file")
    assert "is withheld at this point of the stage and was not run" in said, "the stall guards still read it"
    assert "The tools you may call now: `edit_artifact`, `run_terminal_command`." in said
    assert not BANNED.search(said)


def test_with_none_left_it_says_to_answer():
    middleware = build_settled_answer_middleware(Answer, "defect_fix_1_0", 60)
    middleware._set_withheld({"read_file"}, {"read_file"})
    assert "No tool is left to you: return your structured response now." in _refusal(middleware, "read_file")


def test_with_what_is_left_unrecorded_the_refusal_says_so_plainly():
    middleware = build_settled_answer_middleware(Answer, "defect_fix_1_0", 60)
    middleware._set_withheld({"read_file"})
    said = _refusal(middleware, "read_file")
    assert "Use the tools you were offered on this call." in said and "No tool is left" not in said
