"""A lone surrogate in the conversation is replaced before the request is encoded, so it never fails a run.

Measured on one run: a reply carried `\\ud800`, went back in the conversation, and the next request failed with
`UnicodeEncodeError: surrogates not allowed` - the run failed at the architect.
"""
from __future__ import annotations

import json

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


def test_the_call_path_cleans_before_sending():
    import inspect

    source = inspect.getsource(models)
    assert "messages = _without_lone_surrogates(messages)" in source
