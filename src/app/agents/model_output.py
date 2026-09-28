"""What a model emits around its answer, and what to do about it.

A chat template wraps a turn in delimiters. They are not supposed to reach
content, and across five models in one session they reached it three ways:

- `<|END_THINKING|><|START_ACTION|>` written into `Task.test.mjs`, a syntax
  error on line 963 that broke a 963-line suite (finding 93, one run)
- `<tools>{"name": ...}</tools>` returned as message *content* with
  `tool_calls` empty, so the harness saw no tool call at all (run 40)
- a trailing `</tool_call>` on an otherwise valid structured answer (run 31)

Two callers, two opposite treatments, and the difference matters:

**A write is refused.** Content carrying a delimiter is a turn that was cut off
mid-way, so what would be saved is a truncated transcript rather than the file
the model meant to write. Stripping would save something the model never
finished and leave nobody aware of it. Refusing returns a correction that says
nothing landed and asks for the file again, which is the one thing that
recovers the turn.

**An answer is stripped.** Here the delimiter surrounds something the harness
does want - the structured response - and the reasoning before it is not
corruption, it is the model working. Refusing would throw away a good answer
for the company it arrived in.

The patterns are open by design: a model family that wraps its reasoning some
other way is a line here, not a new bug in each of the four places that would
otherwise have to learn about it separately.
"""

from __future__ import annotations

import re

#: Special tokens in the `<|name|>` spelling every model family uses:
#: `<|im_start|>`, `<|eot_id|>`, `<|END_THINKING|>`, `<|channel|>`.
CONTROL_TOKEN = re.compile(r"<\|[A-Za-z0-9_\-]{1,40}\|>")

#: Reasoning and tool-call wrappers that arrive as plain tags. Paired forms are
#: matched with their contents so stripping removes the whole block; an unpaired
#: closing tag is matched on its own, because a truncated turn leaves one.
_REASONING_BLOCK = re.compile(
    r"<(think|thinking|reasoning|reflection|scratchpad)\b[^>]*>.*?</\1\s*>",
    re.DOTALL | re.IGNORECASE,
)
_STRAY_TAG = re.compile(
    r"</?(think|thinking|reasoning|reflection|scratchpad|tool_call|tools|antml:tool_call)\s*/?>",
    re.IGNORECASE,
)


def find_leaked_marker(text: str) -> str | None:
    """The first delimiter in `text` that should never have been written.

    Used by the write guards, which refuse rather than clean - see the module
    docstring for why.
    """
    if not text:
        return None
    for pattern in (CONTROL_TOKEN, _STRAY_TAG):
        found = pattern.search(text)
        if found is not None:
            return found.group(0)
    return None


def strip_reasoning(text: str) -> str:
    """`text` with reasoning blocks and stray delimiters removed.

    Used when recovering a structured answer, where the delimiters surround
    something wanted. Paired blocks go with their contents - a model that
    reasons about JSON before emitting it would otherwise have the reasoning
    parsed as the answer, which is how a `<think>` block containing an example
    object becomes the response.
    """
    if not text:
        return text
    cleaned = _REASONING_BLOCK.sub(" ", text)
    cleaned = _STRAY_TAG.sub(" ", cleaned)
    cleaned = CONTROL_TOKEN.sub(" ", cleaned)
    return cleaned


__all__ = ["CONTROL_TOKEN", "find_leaked_marker", "strip_reasoning"]
