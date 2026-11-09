"""The deep checks that force the answer tool fall back to `required` where the engine takes only strings.

Measured on an LM Studio server running gpt-oss-20b: a named tool choice is a 400 ("Invalid tool_choice type: 'object'.
Supported string values: none, auto, required"), so four checks that force the answer tool scored 0/3 and the model was
tiered weak for what the engine refuses. `required` with one tool offered forces it just the same.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.models import deep_diagnosis

STRINGS_ONLY = ("Error code: 400 - {'error': \"Invalid tool_choice type: 'object'. Supported string values: "
                "none, auto, required\"}")


class _Server:
    def __init__(self, refuses_named: bool = False, refuses_everything: bool = False):
        self.refuses_named, self.refuses_everything, self.choices = refuses_named, refuses_everything, []

    def create(self, **payload):
        self.choices.append(payload.get("tool_choice"))
        if self.refuses_everything or (self.refuses_named and isinstance(payload.get("tool_choice"), dict)):
            raise RuntimeError(STRINGS_ONLY)
        schema_name = payload["tools"][0]["function"]["name"]
        call = {"id": "c", "type": "function", "function": {"name": schema_name, "arguments": json.dumps(
            {"sprints": [{"goal": "g", "user_value": "v", "in_scope": ["a"], "criteria": ["AC-1"], "out_of_scope": []},
                         {"goal": "h", "user_value": "w", "in_scope": ["b"], "criteria": ["AC-2"], "out_of_scope": []}]})}}
        return {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": "", "tool_calls": [call]}}],
                "usage": {}}


def _model(server):
    return SimpleNamespace(model_name="m", root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)))


def _payload():
    tool = {"type": "function", "function": {"name": "answer", "parameters": {"type": "object"}}}
    return {"model": "m", "tools": [tool], "tool_choice": {"type": "function", "function": {"name": "answer"}},
            "messages": [{"role": "user", "content": "x"}]}


def test_a_server_that_takes_only_strings_is_asked_again_with_required():
    server = _Server(refuses_named=True)

    deep_diagnosis._forced_call(_model(server), **_payload())

    assert server.choices == [{"type": "function", "function": {"name": "answer"}}, "required"]


def test_a_server_that_takes_the_named_form_is_asked_once():
    server = _Server()

    deep_diagnosis._forced_call(_model(server), **_payload())

    assert len(server.choices) == 1 and isinstance(server.choices[0], dict)


def test_a_server_that_refuses_everything_still_raises():
    import pytest

    with pytest.raises(RuntimeError):
        deep_diagnosis._forced_call(_model(_Server(refuses_everything=True)), **_payload())


def test_with_several_tools_offered_required_is_not_a_stand_in_for_one():
    import pytest

    payload = _payload()
    payload["tools"] = [*payload["tools"], {"type": "function", "function": {"name": "other", "parameters": {}}}]

    with pytest.raises(RuntimeError):
        deep_diagnosis._forced_call(_model(_Server(refuses_named=True)), **payload)
