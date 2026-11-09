"""A call wrapping an offered tool's call - its name in one argument, its arguments in another - is taken as that call.

Measured on one run: a sprint planner sent its whole plan as
`Skill({"skill": "SprintPlanOutput", "arguments": {...}})`. `Skill` was not
offered, the call was refused and the plan thrown away, and the next answer,
sent properly, had dropped its success-measure coverage - so planning was
asked again.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.models.tool_arguments import decode_structured_arguments

TOOLS = [
    {"type": "function", "function": {"name": "SprintPlanOutput", "parameters": {
        "type": "object", "properties": {"sprints": {"type": "array"}, "success_measure_coverage": {"type": "array"}},
        "required": ["sprints"]}}},
    {"type": "function", "function": {"name": "read_file", "parameters": {
        "type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}}},
]
PLAN = {"sprints": [{"goal": "Ship the service"}], "success_measure_coverage": ["1: Sprint 1"]}


def _result(name, args):
    return ChatResult(generations=[ChatGeneration(message=AIMessage(
        content="", tool_calls=[{"id": "c1", "name": name, "args": args}]))])


def _call(result):
    return result.generations[0].message.tool_calls[0]


def test_a_wrapped_answer_is_taken_as_the_answer_it_wraps():
    call = _call(decode_structured_arguments(_result("Skill", {"skill": "SprintPlanOutput", "arguments": PLAN}), TOOLS))

    assert call["name"] == "SprintPlanOutput"
    assert call["args"]["success_measure_coverage"] == ["1: Sprint 1"]


def test_a_call_naming_no_offered_tool_is_left_to_its_refusal():
    call = _call(decode_structured_arguments(_result("Skill", {"skill": "deploy_it", "arguments": PLAN}), TOOLS))
    assert call["name"] == "Skill"


def test_an_offered_tool_s_own_call_is_untouched():
    call = _call(decode_structured_arguments(_result("read_file", {"file_path": "app.py"}), TOOLS))
    assert (call["name"], call["args"]) == ("read_file", {"file_path": "app.py"})
