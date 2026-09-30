"""Every stage's answer tool says it is how the stage finishes.

Its description was the schema class's docstring, written for maintainers,
and 35 failed calls on 2026-09-30 were stages writing their answer to a file.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.agents.role_agent import ANSWER_TOOL_DESCRIPTION, the_answer_tool


class Report(BaseModel):
    """Notes for maintainers: mirrors the plan's fields, measured on run 12."""

    summary: str


def test_the_tool_keeps_its_name_and_says_what_it_is_for() -> None:
    from langchain.agents.structured_output import OutputToolBinding, ToolStrategy

    strategy = the_answer_tool(Report)

    assert isinstance(strategy, ToolStrategy)
    tool = OutputToolBinding.from_schema_spec(strategy.schema_specs[0]).tool
    assert tool.name == "Report"
    assert tool.description == ANSWER_TOOL_DESCRIPTION
    assert "maintainers" not in tool.description


def test_anything_but_a_schema_class_is_left_alone() -> None:
    assert the_answer_tool(None) is None
