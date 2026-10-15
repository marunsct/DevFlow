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


def test_a_name_that_could_mean_two_tools_or_none_is_left_alone():
    assert _decoded("read", ("read_command_output", "read_docs")) == "read"
    assert _decoded("SearchBugs", ("ls", "read_file")) == "SearchBugs"
    assert _decoded("read", ("read_file", "read_command_output")) == "read_file"
