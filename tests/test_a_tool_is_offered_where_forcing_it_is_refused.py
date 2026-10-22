"""A server that refuses a forced tool call while the model reasons is offered the tool instead.

A structured answer is asked for by forcing a tool call. Measured on one run:
a hosted frontier model with reasoning on by default answered its first call
with 400 "The tool_choice parameter does not support being set to required or
object in thinking mode", and the run failed there. The call is now asked
again with the tool offered rather than forced, and so is every later call to
that server and model; its reasoning stays on.
"""

from __future__ import annotations

import httpx
import openai
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app import models
from app.models import CompatibleChatOpenAI, refuses_a_forced_tool_while_thinking

TOOL = {"type": "function", "function": {"name": "answer", "parameters": {"type": "object", "properties": {}}}}


def _refusal() -> openai.BadRequestError:
    body = {"error": {"code": "invalid_parameter_error", "message": (
        "The tool_choice parameter does not support being set to required or object in thinking mode")}}
    request = httpx.Request("POST", "https://frontier.example/v1/chat/completions")
    return openai.BadRequestError(f"Error code: 400 - {body}", response=httpx.Response(400, request=request), body=body)


def _model(name: str) -> CompatibleChatOpenAI:
    return CompatibleChatOpenAI(model=name, base_url="https://frontier.example/v1", api_key="k", max_retries=0)


def test_the_refusal_is_recognised_and_nothing_else_is():
    assert refuses_a_forced_tool_while_thinking(_refusal())
    other = openai.BadRequestError(
        "Error code: 400 - context length exceeded",
        response=httpx.Response(400, request=httpx.Request("POST", "https://x")), body=None,
    )
    assert not refuses_a_forced_tool_while_thinking(other)


def test_the_call_is_asked_again_with_the_tool_offered(monkeypatch):
    model = _model("thinks-by-default")
    sent: list = []

    def paced(self, messages, stop=None, run_manager=None, **kwargs):
        payload = self._get_request_payload(messages, stop=stop, **kwargs)
        sent.append(payload.get("tool_choice"))
        if payload.get("tool_choice") not in (None, "auto"):
            raise _refusal()
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    monkeypatch.setattr(CompatibleChatOpenAI, "_generate_paced", paced)
    monkeypatch.setattr(models, "_NO_FORCED_TOOL_WHILE_THINKING", set())
    bound = model.bind_tools([TOOL], tool_choice="any")

    assert bound.invoke([HumanMessage(content="answer")]).content == "ok"
    assert bound.invoke([HumanMessage(content="answer again")]).content == "ok"

    assert sent == ["required", "auto", "auto"], "refused once, then offered from the start"


def test_another_model_still_has_its_tool_forced(monkeypatch):
    monkeypatch.setattr(models, "_NO_FORCED_TOOL_WHILE_THINKING", {("https://frontier.example/v1", "thinks-by-default")})

    payload = _model("answers-plainly").bind_tools([TOOL], tool_choice="any")
    request = payload.bound._get_request_payload([HumanMessage(content="x")], **payload.kwargs)

    assert request["tool_choice"] == "required"


def test_the_refusal_is_remembered_across_a_restart(monkeypatch, tmp_path):
    """Learned once per process, it was learned again after every deploy: one failed request each time."""
    monkeypatch.setenv("FORCED_TOOL_REFUSALS_FILE", str(tmp_path / "refusals.json"))
    monkeypatch.setattr(models, "_NO_FORCED_TOOL_WHILE_THINKING", set())
    models._remember_the_refusal(("https://frontier.example/v1", "thinks-by-default"))

    assert models._refusals_remembered() == {("https://frontier.example/v1", "thinks-by-default")}
