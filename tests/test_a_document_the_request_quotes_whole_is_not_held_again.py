"""A workflow document a stage's request quotes whole is not held again in its memory, and a read of it is pointed
at the request (LF.1469).

Measured on one medium run: the architecture review's request held the specification whole while its memory held it
again as an outline headed "read others by line"; the reviewer read `/docs/technical_specification.md` 46 times in
51 calls. The request and the documents here are that review's opening, captured from the transcript.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import HumanMessage, ToolMessage

from app.agents import project_memory, stage_memory

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CAPTURED = json.loads((Path(__file__).parent / "captured" / "architecture_review_opening.json").read_text("utf-8"))
SPECIFICATION = "docs/technical_specification.md"


class _Request(SimpleNamespace):
    def override(self, **changes):
        return _Request(**{**self.__dict__, **changes})


def _workspace(tmp_path) -> Path:
    for path, text in CAPTURED["files"].items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
    (tmp_path / "task-management-dashboard").mkdir()
    return tmp_path


def _opened(tmp_path, monkeypatch):
    """The review's memory middleware after its first call, and what that call was sent."""
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    memory = project_memory.build_project_memory_middleware(str(_workspace(tmp_path)))
    sent: list = []
    messages = [HumanMessage(content=text) for text in CAPTURED["opening_messages"]]
    memory.wrap_model_call(_Request(messages=messages, model=None), lambda request: sent.append(request.messages))
    return memory, sent[-1]


def test_the_review_s_memory_does_not_hold_the_specification_its_request_quotes(tmp_path, monkeypatch):
    with stage_memory.remembering("an-architecture-review"):
        _, sent = _opened(tmp_path, monkeypatch)
    stage_memory.forget_everything()
    text = "\n".join(str(m.content) for m in sent)

    assert f"=== {SPECIFICATION}" not in text
    assert "read others by line" not in text
    assert project_memory.QUOTED_WHOLE_SAID + SPECIFICATION in text
    # The request's own copy is there, once.
    assert text.count("--- Technical specification and ADRs under review (/docs/technical_specification.md) ---") == 1


def test_a_read_of_it_is_pointed_at_the_request(tmp_path, monkeypatch):
    with stage_memory.remembering("an-architecture-review"):
        memory, _ = _opened(tmp_path, monkeypatch)
        whole = memory.wrap_tool_call(
            SimpleNamespace(tool_call={"name": "read_file", "id": "r1", "args": {"file_path": "/" + SPECIFICATION}}),
            lambda request: ToolMessage(content="the file", tool_call_id="r1"))
        lines = memory.wrap_tool_call(
            SimpleNamespace(tool_call={"name": "read_file", "id": "r2",
                                       "args": {"file_path": SPECIFICATION, "offset": 40, "limit": 20}}),
            lambda request: ToolMessage(content="lines 40-59", tool_call_id="r2"))
    stage_memory.forget_everything()

    assert "quoted whole in your request" in whole.content
    assert lines.content == "lines 40-59"


def test_only_a_document_quoted_whole_is_left_out():
    request = CAPTURED["opening_messages"][1]
    partly = "--- From the approved technical specification: the contracts (/docs/technical_specification.md has the rest) ---"

    assert project_memory.quoted_whole_in(request) == (SPECIFICATION,)
    assert project_memory.quoted_whole_in(partly) == ()


def test_what_it_says_uses_none_of_the_banned_words():
    assert not BANNED.search(project_memory.QUOTED_WHOLE_SAID + project_memory.quoted_whole_pointer(SPECIFICATION))
