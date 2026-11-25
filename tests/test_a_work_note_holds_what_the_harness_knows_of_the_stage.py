"""A stage's work note is written to its real aim, names every file it wrote, keeps what the tools refused, and is
checked against the workspace before it is kept (LF.1466).

Measured on one medium run, a backend builder's eight notes in forty calls: the summariser was shown "Where things
stand" and the stack as the stage's aim, the ask six thousand characters further in; note 4 carried an error "at
line 301" of a file of 276 lines, notes 5 to 8 said "Changed: None" after five writes, and the lesson of what the
command tool refuses was dropped from note 6. Everything here is that stage's real record, captured from the
transcript.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from deepagents.backends import FilesystemBackend
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agents.compaction import RequestKeepingSummarization, aim_of

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CAPTURED = json.loads((Path(__file__).parent / "captured" / "backend_builder_work_notes.json").read_text("utf-8"))
ROUTES = "task-management-dashboard/task_management_dashboard/routes/auth.py"


def _workspace(tmp_path) -> Path:
    for path, text in CAPTURED["files"].items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
    return tmp_path


class Recording(BaseChatModel):
    """The summariser: answers with the note it is given and records what it was asked."""

    note: str = ""
    asked: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "recording"

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs):
        self.asked.append("\n".join(str(m.content) for m in messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.note))])


def _the_stage_s_conversation() -> list:
    """Its real opening request, then its real writes and commands with the real results."""
    messages: list = [HumanMessage(content=CAPTURED["opening_request"], id="opening")]
    for n, call in enumerate(CAPTURED["tool_calls"]):
        messages.append(AIMessage(content="", id=f"ai{n}", tool_calls=[
            {"id": call["id"], "name": call["tool"], "args": call["args"]}]))
        messages.append(ToolMessage(content=call["content"], tool_call_id=call["id"], name=call["tool"], id=f"t{n}"))
    for n, path in enumerate(CAPTURED["written"]):
        messages.append(AIMessage(content="", id=f"w{n}", tool_calls=[
            {"id": f"write{n}", "name": "write_artifact", "args": {"relative_path": path, "content": "..."}}]))
        messages.append(ToolMessage(content='{"path": "%s"}' % path, tool_call_id=f"write{n}", id=f"wt{n}"))
    messages.extend([AIMessage(content="Going on.", id="ai-last"), HumanMessage(content="next", id="h-last")])
    return messages


def _summarised(tmp_path, note: str) -> tuple[str, list]:
    """What the summariser was asked, and the request the stage is sent after the summary."""
    summariser = Recording(note=note, asked=[])
    middleware = RequestKeepingSummarization(
        summariser, backend=FilesystemBackend(root_dir=str(tmp_path)), trigger=("messages", 10),
        keep=("messages", 2), trim_tokens_to_summarize=40_000, repo_root=str(_workspace(tmp_path)),
    )
    seen: list = []

    def handler(request):
        seen.append(request.messages)
        return ModelResponse(result=[AIMessage(content="done")])

    messages = _the_stage_s_conversation()
    middleware.wrap_model_call(
        ModelRequest(model=summariser, messages=messages, state={"messages": messages}, tools=[]), handler)
    return summariser.asked[-1], seen[-1]


def test_the_aim_is_the_work_order_s_ask_not_the_opening_of_the_request():
    aim = aim_of(CAPTURED["opening_request"])

    assert aim.startswith("--- Delegated")
    assert "Create the authentication logic and route handlers for Sprint 1." in aim
    assert "Where things stand" not in aim


def test_a_line_past_its_file_s_end_is_said_to_be_and_a_missing_file_too(tmp_path):
    _, sent = _summarised(tmp_path, CAPTURED["note_4"] + "\n" + CAPTURED["note_2"])
    summary = sent[0].content

    assert re.search(r"routes/auth\.py` \(line 301\)", CAPTURED["note_4"])
    struck = summary.split("(line 301)", 1)[1].split("\n", 1)[0]
    assert "276 lines" in struck
    missing = summary.split("routers/auth.py`", 1)[1].split("\n", 1)[0]
    assert "no such file" in missing
    # A line within its file stands as written.
    assert "schemas.py:64-74`: `LoginRequest`" in summary


def test_the_changed_section_names_every_file_the_stage_wrote(tmp_path):
    assert "## Changed\n- None" in CAPTURED["note_6"]

    _, sent = _summarised(tmp_path, CAPTURED["note_6"])
    changed = sent[0].content.split("## Changed", 1)[1].split("## Left", 1)[0]

    assert all(path in changed for path in CAPTURED["written"])
    assert "- None" not in changed


def test_the_summariser_is_told_the_aim_the_files_written_and_the_refusals(tmp_path):
    asked, sent = _summarised(tmp_path, CAPTURED["note_4"])

    assert "Create the authentication logic and route handlers for Sprint 1." in asked
    assert all(f"`{path}`" in asked for path in CAPTURED["written"])
    assert "'||' is a shell operator and there is no shell here" in asked
    # The stage keeps the refusals under its summary, whatever the note says.
    assert "'||' is a shell operator and there is no shell here" in sent[0].content
    assert "exit 0" in sent[0].content


def test_a_refused_write_is_dropped_once_the_file_is_written(tmp_path):
    """The refused write's "line 301" error is what the notes carried as the file's state after it was written."""
    asked, sent = _summarised(tmp_path, CAPTURED["note_4"])
    refused = "Refusing to write 'task-management-dashboard/task_management_dashboard/auth.py'"

    assert any(refused in call["content"] for call in CAPTURED["tool_calls"])
    ledger = asked.split("What the tools refused", 1)[1].split("Commands the stage ran", 1)[0]
    assert refused not in ledger and refused not in sent[0].content


def test_what_the_ledger_says_uses_none_of_the_banned_words():
    from app.agents import work_note_ledger

    said = (work_note_ledger.for_the_summariser(["a.py"], ["a.py"], ["refused"], ["`ls`: exit 0"])
            + work_note_ledger.for_the_stage(["refused"], ["`ls`: exit 0"])
            + work_note_ledger.with_every_file_written("## Changed\n- None\n## Left\n", ["a.py"])
            + work_note_ledger.checked("`x/a.py:9` `x/b.py`", None))
    assert not BANNED.search(said)
