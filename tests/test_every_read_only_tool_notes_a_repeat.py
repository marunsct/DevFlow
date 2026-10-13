"""Every read-only tool the harness builds says when it is asked the same thing again.

The repeat note is what the settled-answer middleware counts to take a looping
query tool away, and the tools it covered were a list of names - the mistake
this codebase keeps making. `read_command_output` and `changed_since_sprint`
were left off it. One run's fix stage sent one identical `read_command_output`
eight times running; each answer was the same and carried no note, so nothing
counted it. This fails for the next read-only tool nobody adds.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.repeated_queries import QUERY_TOOLS, SAME_ANSWER_MARKER, build_repeated_query_middleware
from app.tools.agent_toolkit import (
    build_journal_read_tool,
    build_repository_read_tools,
    build_sprint_history_tool,
)
from app.tools.package_registry import build_package_lookup_tool

#: Read-only tools with a repeat note of their own.
HAS_ITS_OWN = {"read_file"}


def test_every_read_only_tool_is_covered(tmp_path) -> None:
    built = [
        *build_repository_read_tools(str(tmp_path)),
        build_sprint_history_tool(str(tmp_path)),
        build_journal_read_tool(str(tmp_path)),
        build_package_lookup_tool(),
    ]
    names = {tool.name for tool in built}

    assert names - QUERY_TOOLS - HAS_ITS_OWN == set()


def test_a_journal_read_asked_again_is_noted() -> None:
    middleware = build_repeated_query_middleware()
    call = {"name": "read_command_output", "args": {"reference": "x.log", "search": "AC-9"}, "id": "c"}

    class _Result:
        def __init__(self, content: str) -> None:
            self.content = content

        def model_copy(self, update):
            return _Result(update["content"])

    results = [
        middleware.wrap_tool_call(SimpleNamespace(tool_call=call), lambda request: _Result("48: failed"))
        for _ in range(3)
    ]

    assert SAME_ANSWER_MARKER not in results[0].content
    assert SAME_ANSWER_MARKER in results[-1].content
