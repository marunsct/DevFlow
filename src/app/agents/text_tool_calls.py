"""Recover a tool call the model wrote as text instead of as a tool call.

Some OpenAI-compatible servers do not parse a model's tool-call syntax into the
`tool_calls` field. The model asks for the tool correctly and the harness sees
nothing.

Measured on run 40, Qwen2.5-Coder-7B-Instruct-128K through LM Studio. Asked for
the weather with a tool bound, it returned:

    tool_calls: None
    content   : '<tools>\\n{"name": "get_weather", "arguments": {"location": "Paris"}}\\n</tools>'

The call is right in every respect except the envelope. That run reached
`stack_selector` on answer recovery alone and never wrote a file, because no
tool it asked for ever ran. The model was not incapable; the chat template was
not wired up on the server.

This is deliberately conservative. It fires only when the model returned *no*
tool calls and the content holds something that is unmistakably a call: a
recognised wrapper, or a bare JSON object with exactly the `name`/`arguments`
shape and a name the agent actually has. A model discussing a tool in prose
does not match, and a model whose server works correctly never reaches the
parsing at all.

Left always on rather than switched by a probe. It cannot fire when tool_calls
are already populated, so on a correctly-wired server it is dead weight of one
`if`; and a server that silently stops parsing mid-run - a model swap behind a
proxy, which happened twice in one session - is exactly the case a startup
probe would miss.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

logger = logging.getLogger(__name__)

#: Wrappers seen in the wild, each holding one JSON object per call.
_WRAPPED = re.compile(
    r"<(tools?|tool_call|function_call)\b[^>]*>\s*(?P<body>.*?)\s*</\1\s*>",
    re.DOTALL | re.IGNORECASE,
)

#: A fenced block a model uses when it has been told to emit JSON for a call.
_FENCED = re.compile(r"```(?:json|tool_call)?\s*(?P<body>\{.*?\})\s*```", re.DOTALL)


def _calls_in(body: str, known: set[str]) -> list[dict[str, Any]]:
    """Every well-formed call in one block of text, ignoring anything else."""
    calls: list[dict[str, Any]] = []
    for raw in _json_objects(body):
        try:
            payload = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        name = payload.get("name")
        # `arguments` is the OpenAI spelling; some templates use `parameters`.
        arguments = payload.get("arguments", payload.get("parameters"))
        if not isinstance(name, str) or name not in known:
            continue
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                continue
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            continue
        calls.append(
            {
                "name": name,
                "args": arguments,
                "id": uuid.uuid4().hex[:24],
                "type": "tool_call",
            }
        )
    return calls


def _json_objects(text: str) -> list[str]:
    """Top-level `{...}` spans, by brace depth so nesting survives."""
    spans: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                spans.append(text[start : index + 1])
                start = -1
            elif depth < 0:
                depth = 0
    return spans


def tool_calls_in_text(content: Any, known: set[str]) -> list[dict[str, Any]]:
    """Calls the model wrote into its message text, or an empty list.

    `known` is the set of tools actually bound to this agent. Requiring the
    name to be one of them is what keeps prose about a tool from becoming a
    call to it.
    """
    if not isinstance(content, str) or not content.strip() or not known:
        return []
    calls: list[dict[str, Any]] = []
    for pattern in (_WRAPPED, _FENCED):
        for match in pattern.finditer(content):
            calls.extend(_calls_in(match.group("body"), known))
    if calls:
        return calls
    # No wrapper at all: accept a bare object only if the whole message is one.
    stripped = content.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return _calls_in(stripped, known)
    return []


def build_text_tool_call_middleware() -> Any:
    """Middleware that turns a text-written tool call into a real one."""
    from langchain.agents.middleware import AgentMiddleware

    class TextToolCallMiddleware(AgentMiddleware):
        name = "TextToolCallMiddleware"

        def wrap_model_call(self, request: Any, handler: Any) -> Any:
            response = handler(request)
            try:
                return _recovered(request, response)
            except Exception:  # noqa: BLE001 - never fail a call over a rescue
                logger.debug("Could not inspect a response for text tool calls", exc_info=True)
                return response

    return TextToolCallMiddleware()


def _recovered(request: Any, response: Any) -> Any:
    """`response` with any text-written call promoted to a real tool call."""
    messages = getattr(response, "result", None)
    if not messages:
        return response

    known = {
        getattr(tool, "name", None) or (tool.get("name") if isinstance(tool, dict) else None)
        for tool in (getattr(request, "tools", None) or [])
    }
    known.discard(None)
    if not known:
        return response

    changed = False
    rebuilt = []
    for message in messages:
        if (
            getattr(message, "type", None) == "ai"
            and not getattr(message, "tool_calls", None)
        ):
            calls = tool_calls_in_text(getattr(message, "content", None), known)
            if calls:
                logger.info(
                    "Recovered %d tool call(s) the model wrote as text: %s",
                    len(calls),
                    ", ".join(call["name"] for call in calls),
                )
                message = message.model_copy(
                    update={"tool_calls": calls, "content": ""}
                )
                changed = True
        rebuilt.append(message)

    if not changed:
        return response
    try:
        return response.model_copy(update={"result": rebuilt})
    except AttributeError:
        import dataclasses

        return dataclasses.replace(response, result=rebuilt)


__all__ = ["build_text_tool_call_middleware", "tool_calls_in_text"]
