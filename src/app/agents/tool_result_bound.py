"""A single tool result that by itself would push the next request past the model's context is cut at the tool
(LF.1502).

The summariser makes room by summarising what came before, and the client's guard cuts results to fit
(`app.models.request_fit`); neither helps a result that alone fills what the slot leaves. Such a result keeps its
start and its end, as a long command output does, with a pointer to the rest: a read is read again by line range, any
other result is saved whole and read back with `read_command_output`.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: The tools whose results are a file's lines, read again by range rather than saved.
_READS = frozenset({"read_file"})


def _pointer(tool: str, text: str, repo_root: str | None) -> str:
    if tool in _READS:
        return "read the lines you need with `read_file` and an `offset` and a `limit`"
    from app.tools.journal import scope_of, write_entry

    reference = write_entry(tool or "result", text, scope=scope_of(repo_root))
    if reference:
        return f"the whole result is saved as {reference}; read it with `read_command_output`"
    return "ask for less of it at a time"


def bounded(tool: str, result: Any, repo_root: str | None = None) -> Any:
    """`result` with its text cut to a head and a tail when, whole, it would not fit the stage's next request
    (`request_fit.bounded_result`); `result` itself otherwise. Never raises."""
    try:
        content = getattr(result, "content", None)
        if getattr(result, "type", None) != "tool" or not isinstance(content, str):
            return result
        from app.models import request_fit

        pointer: list[str] = []

        def once() -> str:
            if not pointer:
                pointer.append(_pointer(tool, content, repo_root))
            return pointer[0]

        # Measured first with a placeholder, so a result that fits saves nothing.
        trial = request_fit.bounded_result(content, "")
        if trial is content:
            return result
        return result.model_copy(update={"content": request_fit.bounded_result(content, once())})
    except Exception:  # noqa: BLE001 - the result as the tool gave it
        logger.debug("Could not bound a tool result", exc_info=True)
        return result


def build_middleware(repo_root: str | None = None) -> Any:
    """Middleware that bounds each tool result to what the stage's next request has room for."""
    from langchain.agents.middleware import AgentMiddleware

    class ToolResultBoundMiddleware(AgentMiddleware):
        def wrap_tool_call(self, request: Any, handler: Any) -> Any:
            result = handler(request)
            call = getattr(request, "tool_call", None) or {}
            return bounded(str(call.get("name") or ""), result, repo_root)

        async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
            result = await handler(request)
            call = getattr(request, "tool_call", None) or {}
            return bounded(str(call.get("name") or ""), result, repo_root)

    return ToolResultBoundMiddleware()


__all__ = ["bounded", "build_middleware"]
