"""The owner's steering notes at the end of a request, not in its system message (plan PX.5, behind `STEERING_AT_THE_TAIL`).

Dynamic agent-instruction injection is the owner's feature and stays; only
its position moves. A note added mid-stage was appended to the system
message, which every later call of every stage then carried at the very
start, so the server prefilled the whole conversation again. With the switch
on, the stack's plugin instructions stay in the system message (they are the
same for the whole run) and the owner's direction goes after the transcript,
in the same words, as the last message of the call.
"""

from __future__ import annotations

from app.switches import is_on

#: `STEERING_AT_THE_TAIL` set to on or off overrides this.
ON_BY_DEFAULT = False


def enabled() -> bool:
    return is_on("STEERING_AT_THE_TAIL", ON_BY_DEFAULT)


__all__ = ["ON_BY_DEFAULT", "enabled"]
