"""A salvage request cannot open the model's reasoning again: its tag banned when it is one token, stopped either way.

Given its own reasoning back, closed, a model opened its reasoning tag again
and reasoned on to the ceiling - 173,569 characters, nothing salvaged.
Nothing in the request forbade it. The tag the served template uses, and the
tokens the server makes of it, are found from the server and kept with the
model; a salvage request then bans the tag (`logit_bias`, -100) when
it is one token, and stops at it whatever it is.
"""
from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.models import capabilities, reply_salvage
from app.models.registry import merge_into_fitness


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REPLY_SALVAGE", "on")
    reply_salvage.forget()
    yield
    reply_salvage.forget()


def _tokenizer(tokens):
    def urlopen(request, timeout=None):
        assert request.full_url.endswith("/tokenize")
        assert json.loads(request.data)["content"] == "<think>"
        return io.BytesIO(json.dumps({"tokens": tokens}).encode())
    return urlopen


def test_the_tag_the_template_uses_and_its_one_token_are_found(monkeypatch):
    monkeypatch.setattr(capabilities.urllib.request, "urlopen", _tokenizer([151667]))
    found = capabilities.think_tag_tokens("http://server", {}, "{{ '<|im_start|>assistant\\n<think>\\n' }}")

    assert found["value"] == "<think> = 151667" and found["source"] == "server"
    assert "one token" in found["note"]


def test_a_tag_of_several_tokens_is_kept_as_such(monkeypatch):
    monkeypatch.setattr(capabilities.urllib.request, "urlopen", _tokenizer([27, 26865, 29]))
    found = capabilities.think_tag_tokens("http://server", {}, "<think>")
    merge_into_fitness("m", {capabilities.FOUND_KEY: {"think_tag_tokens": found}})

    assert capabilities.think_ban("m") == ("<think>", None)


def test_a_template_with_no_reasoning_tag_has_none():
    assert capabilities.think_tag_tokens("http://server", {}, "{{ messages }}") is None


def _completion(content):
    return {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


class _Server:
    def __init__(self, replies):
        self.replies, self.sent = list(replies), []

    def create(self, **payload):
        self.sent.append(payload)
        return self.replies.pop(0)


def _model(server):
    def result_of(response):
        message = response["choices"][0]["message"]
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=message.get("content") or ""),
                                                      generation_info={"finish_reason": "stop"})])

    return SimpleNamespace(
        model_name="local-model", openai_api_base="http://server/v1", client=server,
        root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)),
        _get_request_payload=lambda messages, stop=None, **kw: {"model": "local-model", "messages": [
            {"role": "user", "content": "Fix the defect."}], "max_tokens": 32_768, **kw},
        _create_chat_result=result_of,
    )


def _salvaged_with(tag_tokens):
    reply_salvage.keep("local-model", reply_salvage.Support(shape="reasoning_field", tools=True, continuation=True,
                                                            model="local-model"))
    if tag_tokens is not None:
        merge_into_fitness("local-model", {capabilities.FOUND_KEY: {"think_tag_tokens": {
            "value": tag_tokens, "source": "server", "note": ""}}})
    server = _Server([_completion("Changed the status code to 201.")])
    reply_salvage.remember_reasoning("The status code should be 201; the route answers 200.")
    cut = ChatResult(generations=[ChatGeneration(message=AIMessage(content=""), generation_info={"finish_reason": "length"})])
    result = reply_salvage.salvaged(_model(server), [HumanMessage(content="Fix the defect.")], cut)
    assert result.generations[0].message.content == "Changed the status code to 201."
    return server.sent[0]


def test_a_one_token_tag_is_banned_and_stopped_at():
    sent = _salvaged_with("<think> = 151667")
    assert sent["logit_bias"] == {"151667": -100}
    assert sent["stop"] == ["<think>"]


def test_a_tag_of_several_tokens_is_only_stopped_at():
    sent = _salvaged_with("<think> = 27 26865 29")
    assert "logit_bias" not in sent and sent["stop"] == ["<think>"]


def test_an_unknown_tag_leaves_the_request_as_it_was():
    sent = _salvaged_with(None)
    assert "logit_bias" not in sent and "stop" not in sent


class _RefusesTheBan(_Server):
    """A server whose front end rejects `logit_bias`: measured, 400 "logit_bias: Input should be a valid dictionary"."""

    def create(self, **payload):
        self.sent.append(payload)
        if "logit_bias" in payload:
            raise RuntimeError("Error code: 400 - {'error': {'message': 'logit_bias: Input should be a valid dictionary'}}")
        return self.replies.pop(0)


def test_a_server_that_refuses_the_ban_is_asked_again_without_it_and_the_reply_is_still_salvaged():
    reply_salvage.keep("local-model", reply_salvage.Support(shape="reasoning_field", tools=True, continuation=True,
                                                            model="local-model"))
    merge_into_fitness("local-model", {capabilities.FOUND_KEY: {"think_tag_tokens": {
        "value": "<think> = 151667", "source": "server", "note": ""}}})
    server = _RefusesTheBan([_completion("Changed the status code to 201.")])
    reply_salvage.remember_reasoning("The status code should be 201; the route answers 200.")
    cut = ChatResult(generations=[ChatGeneration(message=AIMessage(content=""), generation_info={"finish_reason": "length"})])

    result = reply_salvage.salvaged(_model(server), [HumanMessage(content="Fix the defect.")], cut)

    assert result.generations[0].message.content == "Changed the status code to 201."
    assert "logit_bias" in server.sent[0] and "logit_bias" not in server.sent[1]
    assert server.sent[1]["stop"] == ["<think>"]
