"""A fixer's memory holds whole, after a summary, the files it was reading (LF.1406).

Behind `FIXERS_HOLD_WHAT_THEY_READ`, off until measured.

A summary deletes every file a stage read since its last one. The reviews, the lead, the test rounds, the suite's
author and the builders have their memory chosen again there (LF.1288, `project_memory._chosen_again_at_a_summary`):
the files they wrote, then those they read most, are held whole from the next call. A fix stage was not among them.

Measured on one medium run: two fixers of one batch, summarised two and three times in 17 and 19 calls (their fix
briefs 28-46K characters, the memory sized with them), read the same route, service and entry files again after each
summary - 31 and 27 reads of 10 files, the route module 4 and 7 times, the entry module 3 and 6 - and ended with no
answer and nothing written.

With the switch on, a fix stage joins the stages whose memory is chosen again at a summary, under the same rules and
size gate (a product whose code files all fit is as today) and held to the room its opening left (PA.1). Off in code
until measured: it renders the fixer's memory again at each summary, which the server's cache pays for once.
"""

from __future__ import annotations

import logging

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `FIXERS_HOLD_WHAT_THEY_READ` set to on or off overrides this.
ON_BY_DEFAULT = False
#: The stages this concerns.
FIXING_STAGES = ("defect_fix_",)
#: What the admin page says this switch does.
explanation = ("After each summary of a fix stage's conversation, its project memory holds whole the files it wrote "
               "and those it read most, as the reviews and builders already do, so it does not read them again. The "
               "memory is rendered again at each summary, once.")
#: What the harness records each time a fixer's memory is chosen again; the switch-firing check reads it.
SAID = "A fixer's memory holds the files it was reading after a summary"
#: The transcript record of it.
RECORD_KIND = "fixer_memory_chosen_again"


def enabled() -> bool:
    return is_on("FIXERS_HOLD_WHAT_THEY_READ", ON_BY_DEFAULT)


def is_a_fixer(stage: str) -> bool:
    return str(stage or "").startswith(FIXING_STAGES)


def note(stage: str, held: list[str]) -> None:
    """Record that a fixer's memory now holds `held`. Never raises."""
    try:
        from app.observability.transcript import _run_id_from_config, record

        record(_run_id_from_config(), stage, RECORD_KIND, message=f"{SAID}: " + ", ".join(held[:10]))
    except Exception:  # noqa: BLE001 - a record never fails a call
        logger.debug("Could not record a fixer's memory chosen again", exc_info=True)


__all__ = ["FIXING_STAGES", "ON_BY_DEFAULT", "RECORD_KIND", "SAID", "enabled", "explanation", "is_a_fixer", "note"]
