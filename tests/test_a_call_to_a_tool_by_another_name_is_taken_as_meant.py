"""A call to a tool by another spelling of an offered tool's name is taken as that tool.

Measured on one run: a 1-bit build model called `Read` with `file_path`,
meaning `read_file`, over and over; each was refused as not a valid tool.
"""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage

from app.models.tool_arguments import decode_structured_arguments


def _tool(name):
    return {"type": "function", "function": {"name": name, "parameters": {"type": "object", "properties": {}}}}


def _decoded(name, offered):
    message = AIMessage(content="", tool_calls=[{"name": name, "args": {"file_path": "docs/a.md"}, "id": "c1"}])
    decode_structured_arguments(SimpleNamespace(generations=[SimpleNamespace(message=message)]), [_tool(t) for t in offered])
    return message.tool_calls[0]["name"]


def test_another_spelling_or_the_start_of_an_offered_name_is_that_tool():
    offered = ("ls", "read_file", "glob", "grep", "changed_since_sprint")
    assert _decoded("Read", offered) == "read_file"
    assert _decoded("ReadFile", offered) == "read_file"
    assert _decoded("Grep", offered) == "grep"
    assert _decoded("LS", offered) == "ls"


def test_a_namespace_or_function_prefix_is_stripped_to_match_the_tool():
    offered = ("SprintPlanOutput", "read_file", "ls")
    assert _decoded("functions.SprintPlanOutput", offered) == "SprintPlanOutput"
    assert _decoded("functions.read_file", offered) == "read_file"
    assert _decoded("functions.Read", offered) == "read_file"
    assert _decoded("tools.SprintPlanOutput", offered) == "SprintPlanOutput"


def test_a_name_that_could_mean_two_tools_or_none_is_left_alone():
    assert _decoded("read", ("read_command_output", "read_docs")) == "read"
    assert _decoded("SearchBugs", ("ls", "read_file")) == "SearchBugs"
    assert _decoded("read", ("read_file", "read_command_output")) == "read_file"


def _schema(name, properties, required):
    return {"type": "function", "function": {"name": name, "parameters": {
        "type": "object", "properties": {p: {"type": "string"} for p in properties}, "required": required}}}


def _called(name, args, tools):
    message = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "c1"}])
    decode_structured_arguments(SimpleNamespace(generations=[SimpleNamespace(message=message)]), tools)
    return message.tool_calls[0]["name"]


TOOLS = [_schema("glob", ["pattern", "path"], ["pattern"]),
         _schema("grep", ["pattern", "path", "output_mode", "glob"], ["pattern"]),
         _schema("read_file", ["file_path", "offset", "limit"], ["file_path"])]


def test_a_name_that_says_nothing_is_taken_as_the_one_tool_its_arguments_fit():
    """A 1-bit planner called `global_99` sixteen times with grep's arguments; each was refused."""
    assert _called("global_99", {"pattern": "File Plan", "path": "/docs/spec.md", "output_mode": "content"}, TOOLS) == "grep"
    assert _called("open_it", {"file_path": "docs/a.md", "limit": 10}, TOOLS) == "read_file"


def test_arguments_that_fit_two_tools_or_none_leave_the_call_as_it_was():
    assert _called("global_99", {"pattern": "x", "path": "/tmp"}, TOOLS) == "global_99"
    assert _called("global_99", {"query": "x"}, TOOLS) == "global_99"
    assert _called("global_99", {"path": "/tmp"}, TOOLS) == "global_99"
