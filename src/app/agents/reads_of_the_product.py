"""A stage that judges a suite reads the tests and the documents, never the product's own code (LF.1531).

The QA lead's prompt says "Do not judge the product: whatever part of it is built, it is not the standard ... Never
open its files, even one a test imports". It was only said. Measured on a medium run: the review of a suite written
before its sprint was built sent it back four times, judging the tests by the product as it stood - "the service
returns 405 (Method Not Allowed)" for routes the sprint was about to build, and "models.py has version =
Column(Integer, default=0)" read from the code. A run waited for a person after five rounds.

So a read of a file `file_kinds.classify_file` calls the product's own code ("application") is refused by name for
such a stage - by `read_file` or by a command that only reads it (`shell_reads`, LF.1525); its tests, documents, configuration and the suite's own files still read as before.
"""
from __future__ import annotations

from typing import Any

#: The tools whose result shows a file's text.
READERS = frozenset({"read_file"})

REFUSED = (
    "Not read: `{path}` is the product's own code. This review judges the suite against the acceptance criteria and "
    "the specification, not against what is built so far - tests of what this sprint builds are expected to fail "
    "now. Read the tests, the criteria and the specification instead."
)


def _the_path(args: Any) -> str:
    if not isinstance(args, dict):
        return ""
    return str(args.get("file_path") or args.get("path") or "").strip().lstrip("/")


def refused(tool: str, args: Any) -> str:
    """The refusal of this call, or "" when it reads no product code."""
    if tool == "run_terminal_command" and isinstance(args, dict):
        # A command that only reads a file is a read, whatever tool sends it (LF.1525).
        from app.agents.shell_reads import a_shell_read

        read = a_shell_read(args.get("command"), args.get("working_directory") or "")
        path = read.path if read is not None else ""
    elif tool not in READERS:
        return ""
    else:
        path = _the_path(args)
    if not path:
        return ""
    from app.analysis.file_kinds import classify_file

    return REFUSED.format(path=path) if classify_file(path) == "application" else ""


def build_middleware() -> Any:
    """The middleware that refuses a read of the product's own code."""
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.messages import ToolMessage

    class ReadsOfTheProductMiddleware(AgentMiddleware):
        name = "ReadsOfTheProductMiddleware"

        def wrap_tool_call(self, request: Any, handler: Any) -> Any:
            call = getattr(request, "tool_call", None) or {}
            tool = str(call.get("name") or "")
            said = refused(tool, call.get("args") or {})
            if said:
                return ToolMessage(content=said, tool_call_id=str(call.get("id") or ""), name=tool, status="error")
            return handler(request)

    return ReadsOfTheProductMiddleware()


__all__ = ["READERS", "REFUSED", "build_middleware", "refused"]
