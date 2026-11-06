"""An answer tool called with no arguments, its fields written in the reply's text instead, is answered from the text.

Measured on one run: the architect's core reply - 24,692 output tokens - came back as `TechnicalSpecificationOutput`
called with `{}` and the whole specification as JSON in the text. The empty call was taken: the scope, file plan,
library list, data contracts and decisions were all empty, the other parts were written around nothing, and the
first review found no module planned and no dependency declared.
"""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.models.tool_arguments import decode_structured_arguments

TOOLS = [
    {"type": "function", "function": {"name": "TechnicalSpecificationOutput", "parameters": {
        "type": "object", "properties": {"product_scope": {"type": "string"}, "file_plan": {"type": "array"},
                                         "library_usage": {"type": "array"}}}}},
    {"type": "function", "function": {"name": "read_file", "parameters": {
        "type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}}},
]
CORE = {"product_scope": "A to-do HTTP API.", "file_plan": ["tasks_api/app.py: the routes"],
        "library_usage": ["flask: the routes"]}


def _call(name, args, text):
    result = ChatResult(generations=[ChatGeneration(message=AIMessage(
        content=text, tool_calls=[{"id": "c1", "name": name, "args": args}]))])
    return decode_structured_arguments(result, TOOLS).generations[0].message.tool_calls[0]


def test_the_fields_in_the_text_answer_an_empty_call():
    call = _call("TechnicalSpecificationOutput", {}, json.dumps(CORE, indent=2))
    assert call["args"]["product_scope"] == "A to-do HTTP API."
    assert call["args"]["file_plan"] == ["tasks_api/app.py: the routes"]


def test_fenced_text_is_read_too():
    call = _call("TechnicalSpecificationOutput", {}, "Here it is:\n```json\n" + json.dumps(CORE) + "\n```")
    assert call["args"]["library_usage"] == ["flask: the routes"]


def test_a_call_with_arguments_keeps_them():
    call = _call("TechnicalSpecificationOutput", {"product_scope": "Given"}, json.dumps(CORE))
    assert call["args"]["product_scope"] == "Given"


def test_text_that_is_not_the_answer_s_fields_is_not_taken():
    call = _call("TechnicalSpecificationOutput", {}, json.dumps({"file_path": "x"}))
    assert call["args"] == {}


def test_a_work_tool_called_empty_is_not_filled_from_the_text():
    call = _call("read_file", {}, json.dumps({"file_path": "a.py"}))
    assert call["args"] == {}
