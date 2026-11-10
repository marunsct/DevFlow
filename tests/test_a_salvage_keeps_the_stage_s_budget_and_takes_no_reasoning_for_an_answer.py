"""A salvage keeps the stage's reply budget, and a salvage that only reasons again is no answer.

Measured on one run: a fix stage's reply reasoned to its 12,000-token cap; the cap was cleared before salvage ran, the
16,000 clamp wrote `max_tokens` beside the client's `max_completion_tokens` (the model's 35,000 ceiling, which the
server read), and the reply asked to answer from its reasoning reasoned on in prose to that ceiling - 147,829
characters, 47,000 tokens for one reply, about seven minutes - and was taken as the answer because it had text.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

import app.models as models
from app.agents import settled_answer
from app.models import reply_salvage

REASONING = "The failing test asserts 201; the route returns 200. The fix is the status code in routes.py."
PROSE = " ".join(["Let me trace the flow again.", "Wait, the handler runs first.", "Actually, let me re-read it.",
                  "Hmm, the filter is applied later.", "Let me check the order.", "So what happens next?"] * 20)


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REPLY_SALVAGE", "on")
    reply_salvage.forget()
    yield
    reply_salvage.forget()


def _completion(content="", reasoning="", finish="stop"):
    return {"choices": [{"finish_reason": finish, "message": {
        "role": "assistant", "content": content, "reasoning_content": reasoning, "tool_calls": None}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


class _Server:
    def __init__(self, replies):
        self.replies, self.sent = list(replies), []

    def create(self, **payload):
        self.sent.append(payload)
        return self.replies.pop(0)


def _model(server):
    """A client as langchain-openai builds its payload: the length field is `max_completion_tokens`, at the ceiling."""
    def result_of(response):
        message = response["choices"][0]["message"]
        return ChatResult(generations=[ChatGeneration(
            message=AIMessage(content=message.get("content") or ""),
            generation_info={"finish_reason": response["choices"][0]["finish_reason"]})])

    return SimpleNamespace(
        model_name="local-model", openai_api_base="http://server/v1", client=server, max_tokens=35_000,
        request_timeout=1800, _served_by=lambda: ("http://server/v1", "local-model"),
        root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)),
        _get_request_payload=lambda messages, stop=None, **kw: {"model": "local-model", "messages": [
            {"role": "user", "content": "Fix the defect."}], "max_completion_tokens": 35_000, **kw},
        _create_chat_result=result_of,
    )


def _cut(content=""):
    return ChatResult(generations=[ChatGeneration(
        message=AIMessage(content=content), generation_info={"finish_reason": "length"})])


def _supported(**overrides):
    reply_salvage.keep("local-model", reply_salvage.Support(shape="reasoning_field", tools=True, continuation=True,
                                                            model="local-model", **overrides))


def test_an_answer_from_its_reasoning_is_asked_for_at_most_the_salvage_budget_in_the_client_s_own_field():
    _supported()
    server = _Server([_completion("Changed the status code to 201.")])
    reply_salvage.remember_reasoning(REASONING)
    reply_salvage.salvaged(_model(server), [HumanMessage(content="Fix the defect.")], _cut())
    [sent] = server.sent
    assert sent["max_completion_tokens"] == reply_salvage.SALVAGE_REPLY_TOKENS and "max_tokens" not in sent


def test_an_answer_that_only_reasons_again_is_no_answer_and_no_other_shape_is_tried():
    _supported()
    server = _Server([_completion(PROSE, finish="length"), _completion("Changed the status code to 201.")])
    reply_salvage.remember_reasoning(REASONING)
    result = reply_salvage.salvaged(_model(server), [HumanMessage(content="Fix the defect.")], _cut())
    assert len(server.sent) == 1
    assert result.generations[0].message.content == ""
    assert result.generations[0].generation_info[reply_salvage.SALVAGED] == reply_salvage.FAILED
    assert reply_salvage.reasoned_to_the_cap(PROSE, "length") and not reply_salvage.reasoned_to_the_cap(PROSE, "stop")


def test_a_continuation_is_asked_for_at_most_the_stage_s_cap(monkeypatch):
    _supported()
    monkeypatch.setattr(models, "fix_stage_reply_cap", lambda ceiling: 12_000)
    server = _Server([_completion(" and the route now answers 201.")])
    reply_salvage.salvaged(_model(server), [HumanMessage(content="Fix the defect.")], _cut("I changed routes.py so"))
    assert server.sent[0]["max_completion_tokens"] == 12_000


def test_a_failed_salvage_counts_toward_thinking_off_as_a_lost_reply():
    failed = AIMessage(content="", response_metadata={reply_salvage.SALVAGED: reply_salvage.FAILED})
    assert settled_answer._salvaged_from_its_reasoning(failed)
