"""A defect whose text carries an error the stack pack knows is given that error's cause.

Measured on one run: a delete answered with `c.body('', 204)` threw "Invalid response status code 204" on a Hono
service; the fixers were shown the message, rewrote the handler twice without changing that call, and the sprint was
planned again over a one-line fix. The pack names such errors once (`StackPack.known_errors`); nothing here names a
stack.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: How the cause is introduced in a defect's actual behaviour; never added twice.
KNOWN_CAUSE = "Known cause on this stack:"


def with_known_causes(repo_root: str | Path, defects: list[Any]) -> list[Any]:
    """`defects`, each whose text carries an error the project's pack knows given its cause. Never raises."""
    try:
        from app.stacks import contract

        found = contract.the_pack(Path(repo_root))
        known = dict(getattr(found[0], "known_errors", None) or {}) if found else {}
    except Exception:  # noqa: BLE001 - the defects as raised stand
        return defects
    if not known:
        return defects
    out = []
    for defect in defects:
        text = f"{getattr(defect, 'description', '')} {getattr(defect, 'actual_behavior', '')}".lower()
        actual = str(getattr(defect, "actual_behavior", "") or "")
        causes = [cause for phrase, cause in known.items() if phrase.lower() in text and cause not in actual]
        if causes:
            try:
                defect = defect.model_copy(update={
                    "actual_behavior": (actual + "\n" + "\n".join(f"{KNOWN_CAUSE} {c}" for c in causes)).strip()})
                logger.info("A defect carries an error its stack pack knows; its cause was added")
            except Exception:  # noqa: BLE001 - the defect as raised stands
                pass
        out.append(defect)
    return out


__all__ = ["KNOWN_CAUSE", "with_known_causes"]
