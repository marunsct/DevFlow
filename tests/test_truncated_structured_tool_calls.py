"""Tests for handling truncated structured tool calls.

Proves that:
1. A reply cut off during a tool call (leaving invalid_tool_calls) is not misdiagnosed as all-reasoning.
2. A cut-off answer keeps what arrived whole and instructs the model to generate the remaining fields after the cutoff (not from the beginning).
3. The rest of the answer is joined to what was kept, including combining lists across attempts.
4. Prompt rules ban forbidden words (task, tasks, to-do, todo, button, click, checkbox).
"""

from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel, Field

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.agents.settled_answer import (
    _the_last_reply_was_all_reasoning,
    _replies_that_were_all_reasoning,
)
from app.graph.workflow import _nothing_but_reasoning
from app.models import tool_arguments
from app.models.tool_arguments import (
    CUT_OFF,
    _answer_key,
    _joined_to_what_was_kept,
    _recovered_calls,
    cut_off_notice,
    decode_structured_arguments,
    what_arrived_whole,
)


class SampleSpecificationOutput(BaseModel):
    product_scope: str = Field(..., description="Scope")
    components: list[str] = Field(default_factory=list, description="Components")
    contracts: list[str] = Field(default_factory=list, description="Contracts")
    files: list[str] = Field(default_factory=list, description="Files")


def test_truncated_tool_call_is_not_treated_as_reasoning() -> None:
    """A reply that was writing a tool call when truncated is not all reasoning."""
    msg = AIMessage(
        content="",
        response_metadata={"finish_reason": "length"},
        invalid_tool_calls=[
            {
                "name": "SampleSpecificationOutput",
                "args": '{"product_scope": "Building an API", "components": ["auth"',
                "id": "call_1",
                "error": "Unterminated string",
                "type": "invalid_tool_call",
            }
        ],
    )
    assert _the_last_reply_was_all_reasoning([msg]) is False
    assert _replies_that_were_all_reasoning([msg]) == 0
    assert _nothing_but_reasoning(msg) is False


def test_answer_key_never_returns_none() -> None:
    """_answer_key falls back safely so partial fields are never dropped outside graph context."""
    key = _answer_key("SampleSpecificationOutput")
    assert key is not None
    assert isinstance(key, tuple)
    assert len(key) == 3
    assert key[2] == "SampleSpecificationOutput"


def test_cut_off_notice_instructs_to_continue_after_cutoff_without_banned_words() -> None:
    """The notice tells the model what arrived, not to start from the beginning, without banned words."""
    monkeypatch_held = {("r1", "s1", "SampleSpecificationOutput"): {"product_scope": "API", "components": ["auth"]}}
    original_held = tool_arguments._HELD
    tool_arguments._HELD = monkeypatch_held
    try:
        class DummyCutOffException(Exception):
            pass

        exc = DummyCutOffException(f"Missing required fields; {CUT_OFF}")
        notice = cut_off_notice(exc, SampleSpecificationOutput, stopped_in="contracts", key=("r1", "s1", "SampleSpecificationOutput"))
        assert notice is not None
        assert "contracts" in notice or "files" in notice
        assert "components" in notice
        # Make sure it explicitly says not to start over / not from the beginning
        assert "start over" in notice.lower() or "beginning" in notice.lower() or "continue" in notice.lower()
        # Banned words check
        assert not re.search(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", notice, re.I)
    finally:
        tool_arguments._HELD = original_held


def test_joined_to_what_was_kept_merges_partial_lists_and_remaining_fields() -> None:
    """When the continuation arrives, fields and lists are merged seamlessly."""
    key = ("run-test", "stage-test", "SampleSpecificationOutput")
    tool_arguments._HELD[key] = {
        "product_scope": "API",
        "components": ["auth", "database"],
    }
    try:
        continuation_call: dict[str, Any] = {
            "name": "SampleSpecificationOutput",
            "id": "call_2",
            "args": {
                "components": ["cache"],
                "contracts": ["GET /items"],
                "files": ["src/app.ts"],
            },
        }
        _joined_to_what_was_kept(continuation_call, key=key)
        joined_args = continuation_call["args"]
        assert joined_args["product_scope"] == "API"
        # List components should have combined "auth", "database", and "cache"
        assert joined_args["components"] == ["auth", "database", "cache"]
        assert joined_args["contracts"] == ["GET /items"]
        assert joined_args["files"] == ["src/app.ts"]
        assert key not in tool_arguments._HELD
    finally:
        tool_arguments._HELD.pop(key, None)

