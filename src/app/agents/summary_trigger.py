"""Where a stage's conversation is summarised: past its measured opening, within the room its request has (LF.1606).

Measured live: a backend builder on a server giving each request 93,184 tokens, 32,000 of them held for the reply,
was summarised from 44,147 tokens: 0.8 of an input ceiling that took a constant 6,000 tokens off for the system prompt
and tool schemas (`context_budget.FRAMING_TOKENS`). The count it was compared with is the whole request - the
system prompt, the tool schemas, the specification, the project memory and the request - and that opened at 34,468
reported tokens, 36,000-42,000 after a summary. Since LF.1499 a summarised stage may be summarised again 8 messages
past the tail it kept, so with about 8,000 tokens of conversation between its opening and its trigger it was
summarised about every 75 seconds, 10 times in 14 minutes, and read the same five files 5-6 times each: what it read went into
a summary that keeps only the files' names before it could use them.

The trigger is measured on every call instead: the opening (the next request's tokens, `request_fit.next_request_tokens`,
less its conversation's at the calibrated rate) plus the soft ratio of the room left beside it (the slot less the
reply's reserve, `request_fit.room_tokens`), and never past `request_fit.MARGIN` of that room, which LF.1500's guard
compacts at. It is used only where it is later than the configured trigger; before the stage's first reply reports its
usage, or when the opening alone fills the room (a large codebase's: a summary would gain nothing, and the client's
guard fits the request), the configured trigger stands. A stage whose request opens small on a large window gains a
little: its trigger moves by a fifth of its opening.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: The transcript record of a stage whose request was sent whole past the configured trigger, once per run and stage.
RECORD_KIND = "summarised_past_the_opening"
SAID = "A conversation kept whole past the configured trigger, its opening measured"

_LOCK = threading.Lock()
_NOTED: set[tuple[str, str]] = set()


def trigger_past_the_opening(opening: int, room: int, ratio: float) -> int | None:
    """The tokens a request may reach before its conversation is summarised: `opening` plus `ratio` of what `room`
    leaves beside it, at most `request_fit.MARGIN` of `room`; None when the opening leaves no room or `room` is unknown."""
    from app.models.request_fit import MARGIN

    if room <= 0 or opening < 0:
        return None
    most = int(room * MARGIN)
    if opening >= most:
        return None
    return min(most, opening + int((room - opening) * ratio))


@dataclass(frozen=True)
class Measured:
    """The next request's tokens, its opening's, the room it has and the trigger past that opening."""

    upcoming: int
    opening: int
    room: int
    trigger: int


def measured(messages: list[Any], *, reserve: int | None, window: int | None, ratio: float) -> Measured | None:
    """The trigger past this conversation's opening, or None when it cannot be measured: no reply yet reported its
    usage, the room is unknown, or the opening fills it. Never raises."""
    try:
        from app.models import request_fit

        upcoming = request_fit.next_request_tokens(messages)
        room = request_fit.room_tokens(reserve, window=window)
        first_reply = next((i for i, m in enumerate(messages) if getattr(m, "type", None) == "ai"), None)
        if not upcoming or not room or first_reply is None:
            return None
        conversation = sum(request_fit.message_chars(m) for m in messages[first_reply:])
        opening = max(0, upcoming - int(conversation / request_fit.chars_per_token()))
        trigger = trigger_past_the_opening(opening, room, ratio)
        return Measured(upcoming, opening, room, trigger) if trigger else None
    except Exception:  # noqa: BLE001 - the configured trigger stands
        logger.debug("Could not measure the stage's opening", exc_info=True)
        return None


def note_kept_whole(stage: str, found: Measured, configured: int) -> None:
    """Record, once per run and stage, a request sent whole past the configured trigger. Never raises."""
    try:
        from app.models.model_pin import current_run_id
        from app.observability.transcript import record

        run = current_run_id()
        if not run:
            return
        with _LOCK:
            if (run, stage) in _NOTED:
                return
            _NOTED.add((run, stage))
        record(run, stage, RECORD_KIND, tokens=found.upcoming, opening=found.opening, room=found.room,
               trigger=found.trigger, configured_trigger=configured,
               message=(f"{SAID}: {found.upcoming:,} tokens against {configured:,}; opening {found.opening:,}, "
                        f"room {found.room:,}, summarised at {found.trigger:,}"))
    except Exception:  # noqa: BLE001 - a record never fails a call
        logger.debug("Could not record a request kept whole", exc_info=True)


__all__ = ["Measured", "RECORD_KIND", "SAID", "measured", "note_kept_whole", "trigger_past_the_opening"]
