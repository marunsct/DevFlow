"""Text from outside the run - fetched docs, web pages, search results, MCP answers - defanged before a model reads it (plan SF.2).

Each source already labels its text as data, not instructions, and caps it. A
label is a request; the text under it can still hold what a model, or the
harness's own reader of calls written as text (`app.agents.text_tool_calls`),
takes for a call: a `<tool_call>` block, a `{"name": ..., "arguments": ...}`
object, a chat template's special tokens. A page that carries one is either an
injection attempt or a page about tool calling, and in neither case does the
run need the call's shape to learn from it. So the shapes are replaced with a
marker that says something was there, and the cap applies after.
"""

from __future__ import annotations

import re

MARK = "[tool-call-shaped text removed]"

_WRAPPED = re.compile(
    r"<(tools?|tool_calls?|function_calls?|function|tool_use|invoke)\b[^>]*>.*?</\1\s*>",
    re.DOTALL | re.IGNORECASE,
)
#: An opening wrapper left unclosed (cut by a cap, or written so on purpose).
_OPENING = re.compile(r"</?(?:tools?|tool_calls?|function_calls?|function|tool_use|invoke)\b(?:=[^>\s]*)?[^>]{0,200}>",
                      re.IGNORECASE)
#: A chat template's special tokens: `<|im_start|>`, `<|tool_call_start|>`, `[TOOL_CALLS]`.
_SPECIAL = re.compile(r"<\|[A-Za-z0-9_ .:-]{1,40}\|>|\[/?TOOL_CALLS\]|</?think>", re.IGNORECASE)
#: The head of a JSON call: a name and its arguments; breaking the head breaks the call.
_JSON_CALL = re.compile(
    r"\{\s*\"(?:name|tool|function)\"\s*:\s*\"[^\"]{1,80}\"\s*,\s*\"(?:arguments|args|parameters|input)\"\s*:",
    re.IGNORECASE,
)


def defanged(text: str, limit: int | None = None) -> str:
    """`text` with every tool-call shape replaced by `MARK`, then cut to `limit` characters."""
    out = str(text or "")
    for pattern in (_WRAPPED, _OPENING, _SPECIAL, _JSON_CALL):
        out = pattern.sub(MARK, out)
    return out[:limit] if limit is not None else out


__all__ = ["MARK", "defanged"]
