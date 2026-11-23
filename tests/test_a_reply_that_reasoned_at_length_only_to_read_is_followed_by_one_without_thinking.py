"""With `LONG_REASONING_BEFORE_A_READ` on, the reply after one that reasoned at length and then only read goes without thinking.

Measured on local Qwen3.6 models in one run: replies reasoned 12,000-33,000 tokens (5-7 minutes each) and then made
one or two `read_file` calls - a testing builder five times over, an acceptance-suite author three times, a fix stage
once. None was lost (each ended in a tool call), so no thinking-off rule reached them. With thinking off, the same
stage made each read in about five seconds and then wrote.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import settled_answer, thinking


class _Answer(BaseModel):
    summary: str


class _Request:
    def __init__(self, messages: list, model: Any, settings=None):
        self.messages = messages
        self.model = model
        self.tools = [SimpleNamespace(name="read_file"), SimpleNamespace(name="write_file")]
        self.model_settings = settings or {}

    def override(self, **changes: Any) -> "_Request":
        other = _Request(changes.get("messages", self.messages), changes.get("model", self.model),
                         changes.get("model_settings", self.model_settings))
        other.tools = changes.get("tools", self.tools)
        return other


def _model():
    from app.models import CompatibleChatOpenAI

    return CompatibleChatOpenAI(base_url="http://model-server:8888/v1", api_key="k", model="m", max_tokens=10)


@pytest.fixture(autouse=True)
def _a_server_that_can_switch_thinking_off(monkeypatch, tmp_path):
    monkeypatch.setattr(thinking, "least_reasoning_effort", lambda model: "none")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RUN_TRANSCRIPT", "on")
    monkeypatch.setenv("LONG_REASONING_BEFORE_A_READ", "on")


def _reply(reasoning_tokens: int, *tools: str, reported: bool = True) -> list:
    """A reply that reasoned `reasoning_tokens` and called `tools`, and the results of its calls.

    `reported`: the server reports the reasoning tokens in the usage; else only the reasoning's length in characters
    is known, as from a server that reports none (about four characters a token).
    """
    calls = [{"name": name, "args": {"path": f"src/file_{i}.py"}, "id": f"call-{reasoning_tokens}-{i}"}
             for i, name in enumerate(tools)]
    usage = {"input_tokens": 30_000, "output_tokens": reasoning_tokens + 60, "total_tokens": 30_060 + reasoning_tokens}
    metadata: dict[str, Any] = {"finish_reason": "tool_calls"}
    if reported:
        usage["output_token_details"] = {"reasoning": reasoning_tokens}
    else:
        metadata["reasoning_chars"] = reasoning_tokens * 4
    reply = AIMessage(content="", tool_calls=calls, usage_metadata=usage, response_metadata=metadata)
    return [reply, *(ToolMessage(content="contents", tool_call_id=call["id"], name=call["name"]) for call in calls)]


def _sent(*history: Any) -> _Request:
    seen: dict[str, _Request] = {}

    def handler(request: _Request) -> Any:
        seen["request"] = request
        return SimpleNamespace(result=[])

    middleware = settled_answer.build_settled_answer_middleware(_Answer, "specialist_testing", step_limit=40)
    middleware.wrap_model_call(_Request([HumanMessage(content="Write the unit tests."), *history], _model()), handler)
    return seen["request"]


def _thinking_is_off(request: _Request) -> bool:
    extra = (request.model_settings or {}).get("extra_body") or {}
    return (extra.get("chat_template_kwargs") or {}).get("enable_thinking") is False


@pytest.mark.parametrize("reported", [True, False], ids=["reasoning tokens reported", "only its length known"])
def test_after_twenty_thousand_tokens_of_reasoning_ending_in_a_read_the_next_reply_goes_without_thinking(reported):
    assert _thinking_is_off(_sent(*_reply(20_000, "read_file", reported=reported)))


def test_a_long_deliberation_over_several_reads_turns_thinking_off_too():
    assert _thinking_is_off(_sent(*_reply(15_000, "read_file", "grep", "ls")))


def test_thinking_is_back_on_for_the_reply_after_the_one_without_it():
    assert not _thinking_is_off(_sent(*_reply(20_000, "read_file"), *_reply(40, "read_file")))


@pytest.mark.parametrize("tools", [("write_file",), ("edit_file",), ("execute",), ("read_file", "write_file")])
def test_a_long_deliberation_that_wrote_or_ran_something_keeps_thinking_on(tools):
    assert not _thinking_is_off(_sent(*_reply(20_000, *tools)))


def test_a_read_after_a_short_deliberation_keeps_thinking_on():
    assert not _thinking_is_off(_sent(*_reply(2_000, "read_file")))


def test_with_the_switch_off_a_long_deliberation_over_a_read_keeps_thinking_on(monkeypatch):
    monkeypatch.setenv("LONG_REASONING_BEFORE_A_READ", "off")

    assert not _thinking_is_off(_sent(*_reply(20_000, "read_file")))


def test_each_time_thinking_goes_off_for_it_the_run_s_transcript_says_so_as_the_switch_acting(monkeypatch, tmp_path):
    from app.observability import switch_firing

    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-r")
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: "specialist_testing_3")
    _sent(*_reply(2_000, "read_file"))
    _sent(*_reply(20_000, "read_file"))

    records = [json.loads(line) for line in (tmp_path / "transcripts" / "run-r.jsonl").read_text().splitlines()]
    noted = [r for r in records if r["kind"] != "model_request" and r["kind"] != "model_response"]
    assert [(r["stage"], r["reasoning_tokens"]) for r in noted] == [("specialist_testing_3", 20_000)]
    assert switch_firing.fired(noted) == ["LONG_REASONING_BEFORE_A_READ"]


def _in_one_run_and_stage(monkeypatch, stage="test_round_2"):
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-r")
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "run-r")
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: stage)


def test_after_two_long_deliberations_over_a_read_in_one_stage_thinking_stays_off_for_it(monkeypatch):
    """Measured on one run: a test round reasoned 35,000 tokens before a read twice, thinking back on after each."""
    _in_one_run_and_stage(monkeypatch)
    _sent(*_reply(35_000, "read_file"))
    assert not _thinking_is_off(_sent(*_reply(20_000, "read_file"), *_reply(40, "read_file")))
    _sent(*_reply(35_000, "read_file"))

    assert _thinking_is_off(_sent(*_reply(35_000, "read_file"), *_reply(40, "read_file"), *_reply(60, "edit_file")))


def test_another_stage_does_not_inherit_it(monkeypatch):
    _in_one_run_and_stage(monkeypatch)
    _sent(*_reply(35_000, "read_file"))
    _sent(*_reply(35_000, "read_file"))
    _in_one_run_and_stage(monkeypatch, stage="defect_fix_3_0")

    assert not _thinking_is_off(_sent(*_reply(60, "edit_file")))
