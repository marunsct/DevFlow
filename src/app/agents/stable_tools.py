"""One tool list for a whole stage visit; a withheld tool is refused, not removed (plan PX.2, behind `STABLE_TOOLS`).

Tools are rendered into the system prompt by the chat template, so a list that
changes inside a visit makes the server prefill the whole conversation again.
Measured post hoc on two gate runs (PX.1): a changed tool list was the first
break behind 30-31% of all uncached input tokens. With the switch on, the
guards that withhold a tool - the read tool after redundant reads, one tool
repeated to the same answer, the looking tools of a stalled stage, every tool
but the answer, a spent research share - leave the list as it was bound and
refuse a call to a withheld tool instead (`SettledAnswerMiddleware.wrap_tool_call`),
with the same notice the model is given now. What the model may do is the
same; only where the refusal happens moves.
"""

from __future__ import annotations

from app.switches import is_on

#: `STABLE_TOOLS` set to on or off overrides this.
ON_BY_DEFAULT = False


def enabled() -> bool:
    return is_on("STABLE_TOOLS", ON_BY_DEFAULT)


__all__ = ["ON_BY_DEFAULT", "enabled"]
