"""The conversation is rewritten later when the model's window has room (behind `SUMMARISE_LATER_WITH_HEADROOM`).

Measured on a Java testing stage served by a model with a 91,776-token window: the summariser fired at 50,265 tokens
(0.8 of an input ceiling of 62,832), the stage's own base - system prompt, specification, project memory, tool
schemas - was about 40,000 of them, and the conversation was rewritten every two to five model calls. Each rewrite
drops the tool results the stage had just read, so files were read again. The requests that fired it were counted at
50-57K real input tokens (the count includes the system prompt and tool schemas and matched the usage the model
reported), while the window less the reply's ceiling allows 68,832.

With the switch on, the trigger is 0.95 of the input ceiling instead of 0.8 - in that case 59,690, so the reply's
ceiling (22,944) and 9,000 tokens of margin still fit in the window. The input ceiling already holds back the
reply and the framing, so a trigger below it never sends a request past the window less the reply's room. Where a
configured trigger (`CTX_SOFT_TRIGGER_RATIO`) is already at or past that, nothing changes: no headroom, no effect.
The trigger is fixed when the stage's agent is built, so the request's bytes stay the same within a stage.

Off, the trigger is the policy's, as before. The first call of a stage that the later trigger kept from being
rewritten is recorded once per run and stage (`RECORD_KIND`), so the switch's firing can be read.
"""
from __future__ import annotations

import logging
import threading

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `SUMMARISE_LATER_WITH_HEADROOM` set to on or off overrides this.
ON_BY_DEFAULT = False
NAME = "SUMMARISE_LATER_WITH_HEADROOM"
#: Share of the input ceiling at which the later trigger fires (the policy's is 0.8).
LATER_RATIO = 0.95
#: The transcript record of a stage whose rewrite the later trigger kept off; the switch-firing check reads its `message`.
RECORD_KIND = "summarised_later"
SAID = "A conversation kept whole past the usual trigger, the window having room"

_LOCK = threading.Lock()
_NOTED: set[tuple[str, str]] = set()


def enabled() -> bool:
    return is_on(NAME, ON_BY_DEFAULT)


def trigger_tokens(usual: int, input_ceiling: int) -> int:
    """Where the conversation is rewritten: `usual` when off or with no headroom, else later but below the ceiling.

    The ceiling is what the window leaves once the reply and the framing are held back, so the result is never past it.
    """
    if not enabled():
        return usual
    later = min(int(input_ceiling * LATER_RATIO), input_ceiling)
    return max(usual, later)


def note_kept_whole(stage: str, tokens: int, usual: int, later: int) -> None:
    """Record, once per run and stage, that a request past the usual trigger was sent whole. Never raises."""
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
        record(run, stage, RECORD_KIND, switch=NAME, tokens=tokens, usual_trigger=usual, later_trigger=later,
               message=f"{SAID}: {tokens:,} tokens against {usual:,}, rewritten at {later:,}")
    except Exception:  # noqa: BLE001 - a record never fails a call
        logger.debug("Could not record a later summary", exc_info=True)


__all__ = ["LATER_RATIO", "NAME", "ON_BY_DEFAULT", "RECORD_KIND", "SAID", "enabled", "note_kept_whole",
           "trigger_tokens"]
