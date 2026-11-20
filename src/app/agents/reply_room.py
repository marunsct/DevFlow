"""The tokens kept back for a reply are sized per role family (behind `REPLY_ROOM_SIZED_PER_ROLE`).

One number holds back the reply for every role: on a 91,776-token window it is 32,000 (a quarter of the window,
capped), so a stage's input ceiling is 53,775 and the conversation is rewritten at 43,020. Measured replies are far
shorter for most roles: a specialist's 90th percentile is 1,657 tokens (4,425 in a fix stage), a consultant's 8,052, a
scrum master's 12,258, a principal architect's 14,783, a technical lead's 20,117, the reviews' 10-17,000.

With the switch on, the room accounted for the reply is the larger of 8,000 and twice the role family's 90th percentile
rounded up to 1,000, never above what it was; a role with no row keeps what it was. Only the input ceiling the
conversation is held to follows it - the model's own reply limit (`max_tokens`) is not touched, so a longer reply is
still allowed. It is fixed when the stage's agent is built, so the request's bytes stay the same within a stage.
The stage's first model call records the reservation used, once per run and stage (`RECORD_KIND`).
"""
from __future__ import annotations

import logging
import threading

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `REPLY_ROOM_SIZED_PER_ROLE` set to on or off overrides this.
ON_BY_DEFAULT = False
NAME = "REPLY_ROOM_SIZED_PER_ROLE"
FLOOR_TOKENS = 8_000
#: Measured 90th-percentile reply sizes in tokens, by the role name an agent is built with (a trailing or leading
#: underscore makes it a prefix or a suffix: `specialist_*`, `*_advisor`, `*_advice_reviewer`). A fix stage's
#: specialist is the largest of its kind.
P90_REPLY_TOKENS: dict[str, int] = {
    "specialist_": 4_425,
    "_advisor": 8_052,
    "scrum_master": 12_258,
    "principal_architect": 14_783,
    "technical_lead": 20_117,
    "acceptance_reviewer": 17_000,
    "senior_architect_reviewer": 17_000,
    "security_reviewer": 17_000,
    "milestone_reviewer": 17_000,
    "code_reviewer": 17_000,
    "_advice_reviewer": 17_000,
}
#: The transcript record of a stage's reservation; the switch-firing check reads its `message`.
RECORD_KIND = "reply_room"
SAID = "The room kept for the reply was sized to the role"

_LOCK = threading.Lock()
_NOTED: set[tuple[str, str]] = set()


def enabled() -> bool:
    return is_on(NAME, ON_BY_DEFAULT)


def _p90(role: str) -> int | None:
    for key, value in P90_REPLY_TOKENS.items():
        if (key.endswith("_") and role.startswith(key)) or (key.startswith("_") and role.endswith(key)) or role == key:
            return value
    return None


def reservation(role: str, current: int) -> int:
    """The tokens held back for `role`'s reply: `current` when off, with no row for the role, or when it would not be less."""
    if not enabled() or current <= 0:
        return current
    p90 = _p90(str(role or ""))
    if p90 is None:
        return current
    sized = max(FLOOR_TOKENS, -(-2 * p90 // 1_000) * 1_000)
    return min(sized, current)


def note(stage: str, role: str, reserved: int, current: int) -> None:
    """Record, once per run and stage, the reservation used. Never raises."""
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
        record(run, stage, RECORD_KIND, switch=NAME, role=role, reserved_tokens=reserved, usual_tokens=current,
               message=f"{SAID} {role}: {reserved:,} tokens instead of {current:,}")
    except Exception:  # noqa: BLE001 - a record never fails a call
        logger.debug("Could not record the reply room", exc_info=True)


__all__ = ["NAME", "ON_BY_DEFAULT", "RECORD_KIND", "SAID", "enabled", "note", "reservation"]
