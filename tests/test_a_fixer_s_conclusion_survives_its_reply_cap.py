"""A stage's conclusion survives its reply cap and its summaries; without thinking it is offered only what acts
(plan FX.5, LF.1421).

Measured on one medium run's failing fixers: a fixer reasoned for 12,119 tokens about the migration code and none of
it was carried past the next summary ("Now let me read the full content of the key files"). After a second capped
reply thinking stayed off for the stage with every tool still offered: 24 of 55 calls ran without reasoning, and one
fixer asked for the same held file six times running.
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import settled_answer, stage_memory, thinking, worked_out
from app.models import reply_salvage
from app.models.reply_salvage import SALVAGED
from app.observability import transcript

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CONCLUSION = ("So the cause is settled: database.py looks for alembic/alembic.ini, the file is at the project root, "
              "so the migration block never runs and no table exists. The fix is to point the config at the root.")
REASONING = "Let me look at the migration code once more. " * 300 + "\n\n" + CONCLUSION


class _Answer(BaseModel):
    summary: str


class _Request:
    def __init__(self, messages: list, model: Any, tools: list, settings=None):
        self.messages, self.model, self.tools, self.model_settings = messages, model, tools, settings or {}

    def override(self, **changes: Any) -> "_Request":
        return _Request(changes.get("messages", self.messages), changes.get("model", self.model),
                        changes.get("tools", self.tools), changes.get("model_settings", self.model_settings))


_TOOLS = [SimpleNamespace(name=name) for name in
          ("read_file", "grep", "ls", "write_artifact", "edit_artifact", "run_terminal_command")]


@pytest.fixture(autouse=True)
def _a_fix_stage(monkeypatch):
    stage_memory.forget_everything()
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "defect_fix_2_2")
    monkeypatch.setattr(thinking, "least_reasoning_effort", lambda model: "none")
    monkeypatch.setenv("STABLE_TOOLS", "off")
    monkeypatch.setenv("SALVAGED_REPLIES_TURN_THINKING_OFF", "on")
    yield
    stage_memory.forget_everything()


def _model():
    from app.models import CompatibleChatOpenAI

    return CompatibleChatOpenAI(base_url="http://model-server:8888/v1", api_key="k", model="m", max_tokens=10)


def _capped_reply() -> Any:
    message = AIMessage(content="")
    return SimpleNamespace(generations=[SimpleNamespace(message=message, generation_info={"finish_reason": "length"})])


def _sent(messages: list) -> _Request:
    seen: dict[str, _Request] = {}

    def handler(request: _Request) -> Any:
        seen["request"] = request
        return SimpleNamespace(result=[AIMessage(content="ok")])

    middleware = settled_answer.build_settled_answer_middleware(_Answer, "specialist_backend", step_limit=40)
    middleware.wrap_model_call(_Request(messages, _model(), list(_TOOLS)), handler)
    return seen["request"]


def _salvaged_read(call: str, path: str) -> list:
    """A reply that reasoned to its cap, was answered from its reasoning by salvage, and read a file."""
    return [AIMessage(content="", tool_calls=[{"id": call, "name": "read_file", "args": {"file_path": path}}],
                      response_metadata={SALVAGED: "reasoning", "finish_reason": "tool_calls"}),
            ToolMessage(content=f"     1  # {path}\n     2  value = 1", tool_call_id=call)]


def test_the_end_of_a_capped_reply_s_reasoning_is_pinned_last_in_every_later_request(monkeypatch):
    monkeypatch.setenv("REPLY_SALVAGE", "off")
    with stage_memory.remembering("defect_fix_2_2-thread"):
        reply_salvage.remember_reasoning(REASONING)
        reply_salvage.salvaged(_model(), [], _capped_reply())

        sent = _sent([HumanMessage(content="Fix defect 3."), AIMessage(content="Reading.")])

    last = sent.messages[-1]["content"]
    assert last.startswith(worked_out.HEADING)
    assert CONCLUSION in last
    assert len(last) < len(REASONING) // 3, "the end of it, not all of it"


def test_a_summary_of_the_conversation_does_not_take_it():
    """It is added to each request, never to the stored conversation, so a conversation cut to its summary keeps it."""
    with stage_memory.remembering("defect_fix_2_2-thread"):
        worked_out.keep(REASONING)

        sent = _sent([HumanMessage(content="The request, and a summary of the stage's work so far.")])

    assert CONCLUSION in sent.messages[-1]["content"]


def test_a_stage_with_no_capped_reply_is_sent_as_it_was():
    with stage_memory.remembering("defect_fix_2_2-thread"):
        sent = _sent([HumanMessage(content="Fix defect 3."), AIMessage(content="Reading.")])

    assert not any(worked_out.HEADING in str(m.get("content")) for m in sent.messages if isinstance(m, dict))


def test_once_thinking_is_off_for_the_stage_only_the_tools_that_act_are_offered():
    with stage_memory.remembering("defect_fix_2_2-thread"):
        sent = _sent([HumanMessage(content="Fix defect 3."), *_salvaged_read("r1", "svc/database.py"),
                      *_salvaged_read("r2", "svc/main.py")])

    assert sorted(tool.name for tool in sent.tools) == ["edit_artifact", "run_terminal_command", "write_artifact"]
    assert any(worked_out.ACTING_ONLY_NOTICE in str(m.get("content")) for m in sent.messages if isinstance(m, dict))


def test_thinking_off_for_one_reply_keeps_every_tool():
    with stage_memory.remembering("defect_fix_2_2-thread"):
        sent = _sent([HumanMessage(content="Fix defect 3."), *_salvaged_read("r1", "svc/database.py")])

    assert {tool.name for tool in sent.tools} >= {"read_file", "grep"}


def test_the_new_words_a_model_reads_name_no_banned_words():
    assert not BANNED.search(worked_out.PINNED) and not BANNED.search(worked_out.ACTING_ONLY_NOTICE)
