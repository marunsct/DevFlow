"""A stage's summary is its work note, and a restart of the stage starts from it (PA.2).

Measured on one medium run: the acceptance suite's writer was summarised 74 times in 462 calls. The summariser saw the
latest few file reads and no word of what the stage was for; every summary opened "Establish the foundational backend
architecture for a FastAPI application", described the product's models and routes, and ended "Implement remaining
routers" - nothing of what the stage had found, decided or had left. After each one the stage read the same files
again: 764 reads of 43 files in the run, 17.8 a file; a visit that passed its call ceiling started on an empty
conversation and did the same.
"""
from __future__ import annotations

import re

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from deepagents.backends import FilesystemBackend

from app.agents import stage_memory
from app.agents.carry_over import carry_over_note
from app.agents.compaction import RequestKeepingSummarization

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

REQUEST = (
    "The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
    "You are the QA engineer. The product the earlier sprints built is running. Write the tests of this sprint's "
    "criteria now: AC-7, filtering the list by its status.\n\n--- Acceptance criteria ---\n- AC-7: a list filters by "
    "its status\n" + "More of the request.\n" * 300
)
ROLE = "You write the product's acceptance suite - the tests that decide whether the product is done - and run it."
NOTE = "## Found\n- `shop/app/schemas.py:12` ItemCreate takes `title` and `status`.\n## Left\n- Write `test_ac7.py`."


class Recording(BaseChatModel):
    """The summariser: answers with `NOTE` and records what it was asked."""

    asked: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "recording"

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs):
        self.asked.append("\n".join(str(m.content) for m in messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=NOTE))])


def _a_stage_that_reads(files: int = 12) -> list:
    """A suite writer's conversation: its request, then a read of a large product file a call."""
    messages: list = [HumanMessage(content=REQUEST, id="opening")]
    for n in range(files):
        messages.append(AIMessage(content=f"Reading part {n}.", id=f"ai{n}", tool_calls=[{
            "id": f"read{n}", "name": "read_file", "args": {"file_path": f"shop/app/module_{n}.py"}}]))
        body = "\n".join(f"{k:>6}\tfield_{n}_{k}: str = 'value of line {k}'" for k in range(1, 220))
        messages.append(ToolMessage(content=body, tool_call_id=f"read{n}", id=f"tool{n}"))
    messages.extend([AIMessage(content="Reading on.", id="ai-last"), HumanMessage(content="next", id="h-last")])
    return messages


def _summarised(tmp_path, messages, role: str = "") -> tuple[str, list]:
    """What the summariser was asked, and the request the stage is sent after the summary."""
    summariser = Recording(asked=[])
    middleware = RequestKeepingSummarization(
        summariser, backend=FilesystemBackend(root_dir=str(tmp_path)), trigger=("messages", 10),
        keep=("messages", 4), trim_tokens_to_summarize=4_000, **({"role": role} if role else {}),
    )
    seen: list = []

    def handler(request):
        seen.append(request.messages)
        return ModelResponse(result=[AIMessage(content="done")])

    request = ModelRequest(model=summariser, messages=messages, state={"messages": messages}, tools=[])
    middleware.wrap_model_call(request, handler)
    return summariser.asked[-1], seen[-1]


@pytest.fixture(autouse=True)
def clean_memory():
    stage_memory.forget_everything()
    yield
    stage_memory.forget_everything()


def test_the_summariser_is_told_what_the_stage_was_asked_to_do(tmp_path):
    asked, _ = _summarised(tmp_path, _a_stage_that_reads())

    assert "Write the tests of this sprint's criteria now: AC-7" in asked
    assert "The workspace is rooted" not in asked.split("Messages to summarize:")[1]


def test_the_summariser_is_told_the_stage_s_role(tmp_path):
    asked, _ = _summarised(tmp_path, _a_stage_that_reads(), role=ROLE)

    assert ROLE in asked


def test_the_summariser_is_asked_for_a_work_note_not_the_files(tmp_path):
    asked, _ = _summarised(tmp_path, _a_stage_that_reads())

    for heading in ("## Found", "## Decided", "## Changed", "## Left"):
        assert heading in asked
    assert "`path:line`" in asked
    assert "Do not restate, describe or copy the text of a file" in asked


def test_the_summariser_sees_every_call_of_the_work_it_replaces(tmp_path):
    """The old view was the last few thousand tokens: one or two of the files read, none of the calls before."""
    asked, _ = _summarised(tmp_path, _a_stage_that_reads())

    shown = asked.split("Messages to summarize:")[1]
    assert all(f"shop/app/module_{n}.py" in shown for n in range(10))
    assert "field_0_219" in shown, "a result's end is shown"
    assert "field_0_100:" not in shown, "a read file's middle is the workspace's, not the note's"


def test_the_note_is_in_the_stage_s_next_request_with_the_files_it_read(tmp_path):
    """LF.1285's line naming the files read stays beside the note."""
    _, sent = _summarised(tmp_path, _a_stage_that_reads())

    assert NOTE in sent[0].content
    assert "Files this stage has read so far" in sent[0].content and "`shop/app/module_0.py`" in sent[0].content


def test_a_restart_of_the_stage_starts_from_its_last_work_note(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: "thread-1")
    _summarised(tmp_path, _a_stage_that_reads())

    note = carry_over_note("thread-1", None, "acceptance_author_2", "reached its call ceiling")

    assert "`shop/app/schemas.py:12` ItemCreate takes `title` and `status`" in note
    assert "Write `test_ac7.py`" in note


def test_another_stage_s_note_is_not_carried(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: "thread-1")
    _summarised(tmp_path, _a_stage_that_reads())

    assert carry_over_note("thread-2", None) == ""


def test_a_role_is_the_opening_of_the_system_prompt():
    from app.agents.compaction import role_of

    prompt = ("You are the Testing specialist. You write the product's acceptance suite and run it.\n\n"
              "Rules:\n- many more lines\n" * 3)

    assert role_of(prompt) == "You are the Testing specialist. You write the product's acceptance suite and run it."


def test_a_long_opening_paragraph_is_cut_at_a_sentence():
    from app.agents.compaction import role_of

    prompt = "You are the reviewer. " + "This sentence says more about the role. " * 40

    role = role_of(prompt)

    assert role.startswith("You are the reviewer.") and role.endswith(".") and len(role) <= 600


def test_the_words_the_summariser_and_the_restart_are_given_hold_to_the_house_rules(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: "thread-1")
    asked, _ = _summarised(tmp_path, _a_stage_that_reads(), role=ROLE)
    note = carry_over_note("thread-1", None)

    added = asked.replace(REQUEST.split("\n\n", 1)[1][:1_500], "")
    assert not BANNED.search(added)
    assert not BANNED.search(note.replace(NOTE, ""))
