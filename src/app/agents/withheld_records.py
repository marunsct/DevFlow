"""How a stage's reads were decided while reading was withheld, and how its writes at the call budget went (TR.2, TR.6).

One transcript record per event, read by `loop.sh effects` (`effects_lines`). Records only: nothing here changes what a
stage is offered, refused or told.

- `read_while_withheld`: a read made while the stage's reading was withheld, and how it was decided: refused because
  the project memory holds the file whole, because the same lines are still in the conversation, because the request
  quotes the document whole, or because another rule withheld the read tool whole on that call; or run (LF.1517).
- `write_at_the_budget`: a write made on the calls the budget keeps for the answer: run on a last call (LF.1519), or
  refused because only the answer was left.
"""
from __future__ import annotations

import logging
from collections import Counter

logger = logging.getLogger(__name__)

READ_KIND = "read_while_withheld"
WRITE_KIND = "write_at_the_budget"

#: How a read made while reading was withheld was decided.
HELD_WHOLE = "held whole"
IN_THE_CONVERSATION = "still in the conversation"
QUOTED_WHOLE = "document quoted whole"
WITHHELD_WHOLE = "withheld whole by another rule"
RAN = "ran"
READ_REFUSALS = (HELD_WHOLE, IN_THE_CONVERSATION, QUOTED_WHOLE, WITHHELD_WHOLE)

#: How a write on the budget's last calls went.
REFUSED = "refused"

#: What a call's budget left it, as `settled_answer` records it beside its withheld tools.
LAST_CALLS = "last calls"
ANSWER_ONLY = "answer only"


def _noted(kind: str, **fields: object) -> None:
    try:
        from app.observability.transcript import _run_id_from_config, _stage_from_config, record

        record(_run_id_from_config(), _stage_from_config(""), kind, **fields)
    except Exception:  # noqa: BLE001 - a record must never fail the call it describes
        logger.debug("Could not record %s", kind, exc_info=True)


def noted_read(how: str, path: str, tool: str = "read_file") -> None:
    """One `read_while_withheld` record. Never raises."""
    _noted(READ_KIND, how=how, path=path, tool=tool)


def noted_write(outcome: str, tool: str, path: str = "") -> None:
    """One `write_at_the_budget` record. Never raises."""
    _noted(WRITE_KIND, outcome=outcome, tool=tool, path=path)


def effects_lines(records: list[dict]) -> list[str]:
    """TR.2 and TR.6 for `loop.sh effects`: reads made while reading was withheld, refused by class against run; writes
    at the call budget, refused against run on a last call."""
    reads = Counter(str(r.get("how") or "") for r in records if isinstance(r, dict) and r.get("kind") == READ_KIND)
    writes = Counter(str(r.get("outcome") or "") for r in records if isinstance(r, dict) and r.get("kind") == WRITE_KIND)
    lines = []
    label = "LF.1517 reads while reading was withheld"
    if reads:
        refused = sum(reads[how] for how in READ_REFUSALS)
        lines.append(f"  {sum(reads.values()):>4}  {label}: {reads[RAN]} ran, {refused} refused ("
                     + ", ".join(f"{how} {reads[how]}" for how in READ_REFUSALS) + ")")
    else:
        lines.append(f"     -  {label}: not reached")
    label = "LF.1519 writes on the calls the budget keeps for the answer"
    if writes:
        lines.append(f"  {sum(writes.values()):>4}  {label}: {writes[RAN]} run on a last call, "
                     f"{writes[REFUSED]} refused at the call budget")
    else:
        lines.append(f"     -  {label}: not reached")
    return lines


__all__ = [
    "ANSWER_ONLY", "HELD_WHOLE", "IN_THE_CONVERSATION", "LAST_CALLS", "QUOTED_WHOLE", "RAN", "READ_KIND",
    "READ_REFUSALS", "REFUSED", "WITHHELD_WHOLE", "WRITE_KIND", "effects_lines", "noted_read", "noted_write",
]
