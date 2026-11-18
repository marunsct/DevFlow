"""A model's reply as the text it wrote, whatever form its content takes.

A local server answers with a string. A hosted model answers with a list of blocks: its thinking (with a signature),
then its text, and a tool call as a block of its own. Measured on one hosted run: readers that took
`str(reply.content)` wrote the Python form of that list into five source files, one line each, and the build failed
with 81 syntax errors on line 1. Every reader of a reply's text reads it through `reply_text`.
"""
from __future__ import annotations

from typing import Any

#: Blocks that are not the reply's text: the model's thinking, a provider's reasoning, a redacted one, a tool call.
_NOT_TEXT = frozenset({"thinking", "redacted_thinking", "reasoning", "reasoning_content", "tool_use", "tool_call",
                       "server_tool_use", "function_call", "image"})


def reply_text(reply: Any) -> str:
    """The text of a reply, a message's content, or a list of content blocks; "" for none. Never raises."""
    try:
        content = reply if isinstance(reply, (str, list)) or reply is None else getattr(reply, "content", reply)
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    if str(block.get("type") or "text") in _NOT_TEXT:
                        continue
                    parts.append(str(block.get("text") or ""))
                else:
                    kind = str(getattr(block, "type", "text") or "text")
                    if kind not in _NOT_TEXT:
                        parts.append(str(getattr(block, "text", "") or ""))
            return "".join(parts)
        return str(content)
    except Exception:  # noqa: BLE001 - a reply that cannot be read is no text
        return ""


__all__ = ["reply_text"]
