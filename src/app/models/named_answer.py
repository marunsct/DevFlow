"""On a call where only the answer is allowed, the server is asked for the answer tool by name (plan PA.16, always on).

A stage's answer is a call of its answer tool, and every call of a stage with one is sent `tool_choice: required`
(langchain's tool strategy): some tool must be called, any of them. Where only the answer is left (the call budget
spent, nothing new coming back, a withheld tool called again), the tools are withheld - and with `STABLE_TOOLS` on
they stay on the list, so the prompt prefix the server cached stays valid, and a call to one is refused. Measured on
one medium run: 29 such refusals; another 34. Each is a model call that brings nothing back. The served model's
diagnosis measured the remedy: with `required`, a stage-shaped request called `read_file` first 3 times of 3; with
the answer tool named, it answered 3 of 3.

So on those calls the request names the answer tool (`{"type": "function", "function": {"name": ...}}`); the tool
list itself is sent as it was, byte for byte. Only on a server the model's diagnosis found to honour a named choice
(`structured_answers` "forced", forced with thinking on: `diagnostics.apply`). Anywhere else the call goes as today:
an engine that takes only strings keeps `required`, one that refuses forcing while the model reasons keeps `auto`.
"""
from __future__ import annotations

import contextlib
import contextvars
from typing import Any, Iterator

#: (address, model) of servers whose model was measured to answer a named tool choice with that tool.
HONOURED: set[tuple[str, str]] = set()

_ANSWER: contextvars.ContextVar[str] = contextvars.ContextVar("named_answer", default="")


@contextlib.contextmanager
def naming(tool: str) -> Iterator[None]:
    """The model calls made inside ask for `tool` by name where the server honours it ("" asks for nothing)."""
    token = _ANSWER.set(str(tool or ""))
    try:
        yield
    finally:
        _ANSWER.reset(token)


def asked_for() -> str:
    """The answer tool the model calls made here ask for by name (`naming`), or "" outside such a call."""
    return _ANSWER.get()


def the_answer_tool(schema: Any) -> str:
    """The name the answer tool for `schema` is offered under: the schema's own name (langchain's tool strategy)."""
    return str(getattr(schema, "__name__", "") or "")


def with_the_answer_named(payload: dict, server: tuple[str, str]) -> dict:
    """`payload` asking for the answer tool by name, when a call asked for one (`naming`), `server` honours a named
    choice and the tool is on the payload's list; else as it was. The list is not touched."""
    name = _ANSWER.get()
    if not name or server not in HONOURED or not payload.get("tools"):
        return payload
    offered = {str((tool.get("function") or {}).get("name") or tool.get("name") or "")
               for tool in payload["tools"] if isinstance(tool, dict)}
    if name in offered:
        payload["tool_choice"] = {"type": "function", "function": {"name": name}}
    return payload


__all__ = ["HONOURED", "asked_for", "naming", "the_answer_tool", "with_the_answer_named"]
