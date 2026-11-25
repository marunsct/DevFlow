"""A call where only the answer is allowed asks the server for the answer tool by name (PA.16).

With `STABLE_TOOLS` on, a withheld tool stays on the list and is refused when called; the request still said
`tool_choice: required`, so any tool would do. Measured: 29 and 34 withheld-tool refusals on two medium runs, and the
served model's diagnosis found that under `required` a stage-shaped request called `read_file` first 3 times of 3,
while named it answered 3 of 3. The tool list is sent byte for byte as before; a server that does not honour a named
choice is asked as today.
"""
from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app import models
from app.agents.settled_answer import NOTHING_NEW_BEFORE_THE_ANSWER, build_settled_answer_middleware
from app.models import CompatibleChatOpenAI, diagnostics

ADDRESS, MODEL = "http://local.example/v1", "local-model"
TOOLS = [{"type": "function", "function": {"name": name, "description": f"{name} a path",
                                           "parameters": {"type": "object", "properties": {}}}}
         for name in ("glob", "ls", "read_file")]
SAME = "[This `glob` returned exactly what it returned the 3 previous times you ran it in this stage.]"


class Spec(BaseModel):
    product_scope: str


class _Request:
    def __init__(self, messages, tools):
        self.messages, self.tools, self.model = messages, tools, None

    def override(self, **changes):
        return _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))


def _stage(results: list[str]) -> list:
    messages: list = [HumanMessage(content="write the specification")]
    for index, result in enumerate(results):
        tool = ("glob", "ls", "read_file")[index % 3]
        messages.append(AIMessage(content="", id=f"a{index}",
                                  tool_calls=[{"name": tool, "args": {"pattern": "docs/*"}, "id": f"c{index}"}]))
        messages.append(ToolMessage(content=result, tool_call_id=f"c{index}"))
    return messages


def _diagnosed(structured: str, only_without_thinking: bool = False) -> diagnostics.Diagnosis:
    settings = diagnostics.Settings(structured, only_without_thinking, "", False, ())
    return diagnostics.Diagnosis(MODEL, "2026-11-25T00:00:00+00:00", (), {}, settings)


def _payload_sent(monkeypatch, results: list[str], structured: str = "forced") -> dict:
    """The request body the model server receives for the stage's next call, its model diagnosed `structured`."""
    monkeypatch.setenv("STABLE_TOOLS", "on")
    monkeypatch.setattr(models, "_NAMED_CHOICE_BECOMES_REQUIRED", set())
    monkeypatch.setattr(models, "_NO_FORCED_TOOL_WHILE_THINKING", set())
    client = CompatibleChatOpenAI(model=MODEL, base_url=ADDRESS, api_key="k", max_retries=0)
    diagnostics.apply(client, _diagnosed(structured))
    answer = {"type": "function", "function": {"name": "Spec", "description": "the answer",
                                               "parameters": Spec.model_json_schema()}}

    def the_server(request):
        # As the agent binds a stage with a structured answer: its tools, the answer tool, a tool required.
        described = {tool["function"]["name"]: tool for tool in TOOLS}
        bound = client.bind_tools([*(described[tool.name] for tool in request.tools), answer], tool_choice="required")
        return bound.bound._get_request_payload([HumanMessage(content="x")], **bound.kwargs)

    middleware = build_settled_answer_middleware(Spec, "principal_architect", 120)
    tools = [SimpleNamespace(name=tool["function"]["name"]) for tool in TOOLS]
    return middleware.wrap_model_call(_Request(_stage(results), tools), the_server)


LEFT_ONLY_THE_ANSWER = ["docs/technical_specification.md"] + [SAME] * NOTHING_NEW_BEFORE_THE_ANSWER
STILL_WORKING = [SAME] * (NOTHING_NEW_BEFORE_THE_ANSWER - 1) + ["docs/technical_specification.md"]


def test_a_call_left_only_its_answer_names_the_answer_tool_and_keeps_the_list(monkeypatch):
    working = _payload_sent(monkeypatch, STILL_WORKING)
    answering = _payload_sent(monkeypatch, LEFT_ONLY_THE_ANSWER)

    assert answering["tool_choice"] == {"type": "function", "function": {"name": "Spec"}}
    assert answering["tools"] == working["tools"]
    assert [tool["function"]["name"] for tool in answering["tools"]] == ["glob", "ls", "read_file", "Spec"]


def test_a_call_still_working_requires_a_tool_as_before(monkeypatch):
    assert _payload_sent(monkeypatch, STILL_WORKING)["tool_choice"] == "required"


def test_a_server_that_takes_only_string_choices_is_asked_as_today(monkeypatch):
    assert _payload_sent(monkeypatch, LEFT_ONLY_THE_ANSWER, structured="required")["tool_choice"] == "required"


def test_a_server_that_cannot_force_while_reasoning_is_asked_as_today(monkeypatch):
    assert _payload_sent(monkeypatch, LEFT_ONLY_THE_ANSWER, structured="offered")["tool_choice"] == "auto"


def test_the_named_choice_ends_with_the_call(monkeypatch):
    _payload_sent(monkeypatch, LEFT_ONLY_THE_ANSWER)
    client = CompatibleChatOpenAI(model=MODEL, base_url=ADDRESS, api_key="k", max_retries=0)
    bound = client.bind_tools(TOOLS, tool_choice="required")

    assert bound.bound._get_request_payload([HumanMessage(content="x")], **bound.kwargs)["tool_choice"] == "required"
