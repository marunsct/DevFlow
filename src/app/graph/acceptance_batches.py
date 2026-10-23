"""The acceptance suite written in batches of criteria, when the model finds the whole of it too much (behind `BATCH_ACCEPTANCE_AUTHOR`).

Measured on one run: a model that reasons at length wrote the whole suite - 39 tests for 20
criteria - in 14 replies of about 17,000 tokens, 65 minutes, where earlier runs used 1,000-2,000
tokens a reply and eight minutes. A criterion is the unit: each carries its id into its tests'
names, so `suite.coverage` says exactly which are written, and a batch is done when its criteria
are covered - which also makes the stage resumable with no state of its own.

How big a batch is follows how the model was measured (`app.models.guidance` tier): a strong
model, or one never measured, gets one batch, the request it always had. Design and the other
stages: `docs/work-batching.md`.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `BATCH_ACCEPTANCE_AUTHOR` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Criteria in one batch, by the model's tier; None is all of them at once.
CRITERIA_A_BATCH: dict[str, int | None] = {"strong": None, "standard": 8, "weak": 4}
#: Fewest criteria worth a second batch: below it the split costs more than it saves.
LEAST_TO_SPLIT = 6


def enabled() -> bool:
    return is_on("BATCH_ACCEPTANCE_AUTHOR", ON_BY_DEFAULT)


def batch_size(model: str = "") -> int | None:
    """Criteria in one batch for the serving model; None when it takes them all at once."""
    try:
        from app.models.guidance import recorded
        from app.models.model_guidance import served_now

        profile = recorded(model or served_now())
    except Exception:  # noqa: BLE001 - never measured: the request it always had
        return None
    return CRITERIA_A_BATCH.get(getattr(profile, "tier", "") or "")


def groups(criteria: Sequence[Any], size: int | None) -> list[list[Any]]:
    """The criteria in order, in batches of at most `size`, the last never a stub; one batch when `size` is None or small."""
    items = list(criteria)
    if not size or len(items) < max(LEAST_TO_SPLIT, size + 1):
        return [items]
    count = -(-len(items) // size)
    base, extra = divmod(len(items), count)  # as even as the count allows, so the last is no stub
    out, at = [], 0
    for number in range(count):
        step = base + (1 if number < extra else 0)
        out.append(items[at:at + step])
        at += step
    return out


def plan(criteria: Sequence[Any], *, model: str = "") -> list[list[Any]]:
    """The batches the suite is written in now: one (today's request) unless the switch is on and the model needs more."""
    wanted = groups(criteria, batch_size(model))
    if len(wanted) > 1 and not enabled():
        logger.info("Work split planned, not made (BATCH_ACCEPTANCE_AUTHOR is off): %d criteria in %d batches",
                    len(list(criteria)), len(wanted))
        return [list(criteria)]
    return wanted


def note(index: int, total: int, group: Sequence[Any], files: Sequence[str]) -> str:
    """What a batch is told of the others, after its criteria."""
    ids = ", ".join(c.id for c in group)
    if index == 0:
        return (
            f"--- This suite is written in {total} parts ---\n"
            f"You write part 1 of {total}: the criteria above, {ids}. Also write what the later parts will share "
            "- helpers, fixtures, how the product is started - in the suite's own files, so they can use it. "
            "Later parts cover the other criteria; leave those to them.\n\n"
        )
    written = ", ".join(f"`{name}`" for name in files) or "the suite's files"
    return (
        f"--- This suite is written in {total} parts ---\n"
        f"You write part {index + 1} of {total}: the criteria above, {ids}. Earlier parts already wrote {written}; "
        "they are in the project memory. Reuse their helpers and fixtures instead of writing them again, and do not "
        "rewrite or remove their tests. Put yours in a new file beside them named in the same way, or add to one of "
        "theirs. Each test name carries the id of the criterion it proves. Leave the other criteria to the other "
        "parts.\n\n"
    )


__all__ = ["CRITERIA_A_BATCH", "ON_BY_DEFAULT", "enabled", "groups", "note", "plan"]
