"""What a call says about its withheld tools is one true list: no older block claims a tool works that the call refuses.

Measured on a live fixer (tool review TR.3, LF.1518): on its last two calls one message said "Reading and running are
withheld from here", "`grep` and the directory listings still work, and so does everything that changes a file or runs
a command", "Everything else still works" and "refused if called on this call: every tool except `delete_artifact`,
`edit_artifact`, `write_artifact`" - and the fixer had no directory listing at all. The refusal just before it listed
`grep` and `run_terminal_command` as callable now; the next call, the only one that could act on it, refused both.
The conversation is the fixer's own, captured from its request.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import stage_memory
from app.agents.settled_answer import build_settled_answer_middleware

CAPTURED = json.loads((Path(__file__).parent / "captured" / "fixer-reads-withheld-after-two-summaries.json")
                      .read_text(encoding="utf-8"))
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
#: Every tool name a notice of this harness might name, offered here or not.
TOOL_NAMES = {*CAPTURED["offered"], "ls", "glob", "grep", "read_file", "move_artifact", "replace_lines",
              "run_validation", "look_up_package", "look_at_page", "read_docs", "edit_file", "write_file", "execute"}
WRITERS = {"delete_artifact", "edit_artifact", "write_artifact"}


class Answer(BaseModel):
    changed_files: list[str]


class _Request(SimpleNamespace):
    def override(self, **changes):
        return _Request(**{**self.__dict__, **changes})


def _message(m: dict):
    if m["type"] == "ai":
        return AIMessage(content=m["content"], tool_calls=m["tool_calls"])
    return ToolMessage(content=m["content"], tool_call_id=m["tool_call_id"], name=m["name"])


def _after_the_refused_reads() -> list:
    """The captured conversation, then its next reply's four reads, each refused as the fixer's were."""
    return [HumanMessage(content="Fix the failing unit tests"),
            *(_message(m) for m in CAPTURED["conversation"]),
            _message(CAPTURED["reply"]),
            *(ToolMessage(content=CAPTURED["refusal"], tool_call_id=call["id"], name="read_file")
              for call in CAPTURED["reply"]["tool_calls"])]


def _calls(messages) -> int:
    return sum(1 for m in messages if isinstance(m, AIMessage))


def _sent(monkeypatch, calls_left: int):
    """The guard with a budget leaving `calls_left` calls (this one included), and the request it sends."""
    monkeypatch.setenv("STABLE_TOOLS", "on")
    monkeypatch.setenv("FIX_STAGE_CALL_CAP", "off")
    messages = _after_the_refused_reads()
    guard = build_settled_answer_middleware(Answer, "defect_fix_2_1", _calls(messages) + calls_left)
    sent: list = []
    guard.wrap_model_call(_Request(messages=messages, model=None, model_settings={},
                                   tools=[SimpleNamespace(name=name) for name in CAPTURED["offered"]]), sent.append)
    return guard, str(sent[0].messages[-1]["content"])


def test_the_notice_on_the_last_two_calls_names_no_tool_the_stage_was_not_offered(monkeypatch):
    with stage_memory.remembering("a-fixer-thread"):
        _, said = _sent(monkeypatch, calls_left=2)
    stage_memory.forget_everything()

    named = set(re.findall(r"`([a-z_]+)`", said)) & TOOL_NAMES
    assert named <= set(CAPTURED["offered"])
    assert "listing" not in said, "the stage is offered no directory listing"


def test_no_sentence_says_a_tool_works_that_the_call_refuses(monkeypatch):
    with stage_memory.remembering("a-fixer-thread"):
        _, said = _sent(monkeypatch, calls_left=2)
    stage_memory.forget_everything()

    assert "every tool except `delete_artifact`, `edit_artifact`, `write_artifact`" in said
    assert not re.search(r"still works?\b", said)
    assert "run the check" not in said, "running is refused on these calls"
    assert not BANNED.search(said)


def test_a_refusal_lists_what_the_next_call_allows(monkeypatch):
    """Three calls left: the reads are withheld on this one, and the next is one of the budget's last two."""
    with stage_memory.remembering("a-fixer-thread"):
        guard, _ = _sent(monkeypatch, calls_left=3)
        refusal = guard.wrap_tool_call(
            SimpleNamespace(tool_call={"name": "read_file", "id": "r9", "args": {"file_path": "tasks-api/README.md"}}),
            lambda request: "ran")
    stage_memory.forget_everything()

    said = str(refusal.content)
    listed = set(re.findall(r"`([a-z_]+)`", said.split("may call now:", 1)[1]))
    assert listed == WRITERS
