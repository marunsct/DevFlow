"""A lone surrogate in the conversation is replaced before the request is encoded, so it never fails a run.

Measured on one run: a reply carried `\\ud800`, went back in the conversation, and the next request failed with
`UnicodeEncodeError: surrogates not allowed` - the run failed at the architect.
"""
from __future__ import annotations

import json

import httpx
from langchain_core.messages import AIMessage, HumanMessage

from app import models


def test_every_string_is_made_encodable():
    bad = "a\ud800b"
    messages = [HumanMessage(content="fine"), AIMessage(content=bad, additional_kwargs={"reasoning_content": bad},
                                                       tool_calls=[{"name": "t", "args": {"x": bad}, "id": "1"}])]
    out = models._without_lone_surrogates(messages)
    assert out[0] is messages[0], "a message with none is sent as it was"
    json.dumps([m.model_dump() for m in out], ensure_ascii=False).encode("utf-8")
    assert out[1].content == "a�b"
    assert out[1].additional_kwargs["reasoning_content"] == "a�b"
    assert out[1].tool_calls[0]["args"]["x"] == "a�b"


def test_a_list_content_is_cleaned_too():
    out = models._without_lone_surrogates([HumanMessage(content=[{"type": "text", "text": "x\udc80"}])])
    assert out[0].content[0]["text"] == "x�"


def test_a_conversation_carrying_one_is_still_sent(tmp_path, monkeypatch):
    """The request that leaves for the model server: encodable, the surrogate replaced."""
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    sent = []

    def server(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        })

    model = models.CompatibleChatOpenAI(
        model="m", base_url="http://gpu:9090/v1", api_key="k", max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(server)),
    )

    model.invoke([HumanMessage(content="fine"), AIMessage(content="a\ud800b"), HumanMessage(content="go on")])

    assert [message["content"] for message in sent[0]["messages"]] == ["fine", "a�b", "go on"]
