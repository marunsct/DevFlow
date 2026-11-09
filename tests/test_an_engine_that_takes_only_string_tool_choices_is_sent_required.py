"""An engine that refuses a named tool choice but enforces `required` is sent `required`, not `auto`.

Measured on an LM Studio server running gpt-oss-20b: a named `tool_choice` is a 400 ("Invalid tool_choice type: 'object'.
Supported string values: none, auto, required"). The diagnosis read that as "forcing does not work" and the client then
rewrote every forced choice, `required` included, to `auto`. With `auto` the model's output failed the engine's own parser
("does not match the expected peg-native format"): 0 or 1 replies in 3 answered, and the consult stages failed on every
attempt. With `required` all 3 answered.
"""
from __future__ import annotations

import httpx
import openai
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app import models
from app.models import CompatibleChatOpenAI, diagnostics, takes_only_string_tool_choices

TOOL = {"type": "function", "function": {"name": "answer", "parameters": {"type": "object", "properties": {}}}}
NAMED = {"type": "function", "function": {"name": "answer"}}
STRINGS_ONLY = ("Invalid tool_choice type: 'object'. Supported string values: none, auto, required")


def _refusal() -> openai.BadRequestError:
    body = {"error": STRINGS_ONLY}
    request = httpx.Request("POST", "http://lm.example/v1/chat/completions")
    return openai.BadRequestError(f"Error code: 400 - {body}", response=httpx.Response(400, request=request), body=body)


def _check(name, passed, tries=3, notes=()):
    return diagnostics.Check(name=name, passed=passed, tries=tries, refused=tries - passed if not passed else 0, notes=tuple(notes))


def _checks(*, named_works, required_works=True, required_stage=True, only_strings=True):
    note = (f"refused: Error code: 400 - {{'error': \"{STRINGS_ONLY}\"}}",) if only_strings else ("refused: other",)
    named = lambda name: _check(name, 3 if named_works else 0, notes=() if named_works else note)  # noqa: E731
    return [
        _check("tools offered", 3), _check("a tool required", 3 if required_works else 0),
        named("one tool named"), named("one tool named, thinking off"), _check("only offered names", 3),
        named("a structured answer forced"), _check("a structured answer, offered", 0),
        _check("a structured answer, required", 3 if required_stage else 0), named("forced after a long request"),
    ]


def test_the_refusal_is_recognised_and_no_other():
    assert takes_only_string_tool_choices(_refusal())
    other = openai.BadRequestError("Error code: 400 - context length exceeded",
                                   response=httpx.Response(400, request=httpx.Request("POST", "https://x")), body=None)
    assert not takes_only_string_tool_choices(other)


def test_an_engine_that_refuses_the_named_form_but_enforces_required_is_settled_on_required():
    settings = diagnostics.settled(_checks(named_works=False), {})

    assert settings.structured_answers == "required"
    assert any("sent as `required`" in line for line in settings.advice)


def test_an_engine_that_cannot_force_at_all_is_still_offered():
    # `required` does not work either: forcing is not available.
    assert diagnostics.settled(_checks(named_works=False, required_works=False), {}).structured_answers == "offered"
    # `required` works on a small request but not on a stage-shaped one.
    assert diagnostics.settled(_checks(named_works=False, required_stage=False), {}).structured_answers == "offered"
    # The refusal is about something else than the type of the choice.
    assert diagnostics.settled(_checks(named_works=False, only_strings=False), {}).structured_answers == "offered"


def test_an_engine_that_forces_by_name_is_forced_as_before():
    assert diagnostics.settled(_checks(named_works=True), {}).structured_answers == "forced"


def _client(monkeypatch, name="lm-model"):
    monkeypatch.setattr(models, "_NAMED_CHOICE_BECOMES_REQUIRED", set())
    monkeypatch.setattr(models, "_NO_FORCED_TOOL_WHILE_THINKING", set())
    return CompatibleChatOpenAI(model=name, base_url="http://lm.example/v1", api_key="k", max_retries=0)


def _payload(client, choice):
    bound = client.bind_tools([TOOL], tool_choice=choice)
    return bound.bound._get_request_payload([HumanMessage(content="x")], **bound.kwargs)


def test_a_server_known_to_take_only_strings_gets_required_for_a_named_choice_and_keeps_required(monkeypatch):
    client = _client(monkeypatch)
    models._NAMED_CHOICE_BECOMES_REQUIRED.add(("http://lm.example/v1", "lm-model"))

    assert _payload(client, "answer")["tool_choice"] == "required"
    assert _payload(client, "any")["tool_choice"] == "required"
    assert _payload(client, "auto")["tool_choice"] == "auto"


def test_another_server_keeps_its_named_choice(monkeypatch):
    client = _client(monkeypatch)

    assert _payload(client, "answer")["tool_choice"] == NAMED


def test_the_first_refusal_teaches_the_client_and_the_call_is_asked_again_with_required(monkeypatch):
    client = _client(monkeypatch)
    sent: list = []

    def paced(self, messages, stop=None, run_manager=None, **kwargs):
        payload = self._get_request_payload(messages, stop=stop, **kwargs)
        sent.append(payload.get("tool_choice"))
        if isinstance(payload.get("tool_choice"), dict):
            raise _refusal()
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    monkeypatch.setattr(CompatibleChatOpenAI, "_generate_paced", paced)
    bound = client.bind_tools([TOOL], tool_choice="answer")

    assert bound.invoke([HumanMessage(content="a")]).content == "ok"
    assert bound.invoke([HumanMessage(content="b")]).content == "ok"

    assert sent == [NAMED, "required", "required"]


def test_apply_teaches_the_client_and_does_not_switch_forcing_off(monkeypatch):
    client = _client(monkeypatch)
    settings = diagnostics.Settings(structured_answers="required")
    diagnosis = diagnostics.Diagnosis("lm-model", "2026-10-24T00:00:00+00:00", (), {}, settings)

    diagnostics.apply(client, diagnosis)

    server = ("http://lm.example/v1", "lm-model")
    assert server in models._NAMED_CHOICE_BECOMES_REQUIRED and server not in models._NO_FORCED_TOOL_WHILE_THINKING
